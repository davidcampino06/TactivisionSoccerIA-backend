"""Temporary lock after repeated failed logins (protection against password guessing).

Failed attempts per e-mail live in a HashTable (data_structures.py): O(1) average to check,
record or clear an e-mail. After ``max_failed`` failures inside the window the account is locked
for ``lock_minutes``. A successful login clears the counter. Kept in memory: a restart resets it.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from config import settings
from data_structures import HashTable
from singleton import SingletonMeta


@dataclass
class _AttemptRecord:
    failures: int
    first_failure_at: float
    locked_until: float = 0.0


class LoginAttemptTracker(metaclass=SingletonMeta):
    def __init__(self, max_failed: int | None = None, lock_minutes: int | None = None, clock=time.monotonic) -> None:
        self.max_failed = max_failed or settings.login_max_failed_attempts
        self.lock_seconds = (lock_minutes or settings.login_lock_minutes) * 60
        self._clock = clock
        self._records: HashTable[str, _AttemptRecord] = HashTable()
        self._lock = threading.Lock()

    def seconds_locked(self, email: str) -> int:
        """Remaining lock time in seconds (0 = not locked)."""
        with self._lock:
            record = self._records.get(email)
            if record is None:
                return 0
            remaining = record.locked_until - self._clock()
            return max(0, int(remaining + 0.999))

    def record_failure(self, email: str) -> int:
        """Register a failed attempt. Returns the remaining attempts before the lock (0 = now locked)."""
        with self._lock:
            now = self._clock()
            record = self._records.get(email)
            if record is None or now - record.first_failure_at > self.lock_seconds:
                record = _AttemptRecord(failures=0, first_failure_at=now)
            record.failures += 1
            if record.failures >= self.max_failed:
                record.locked_until = now + self.lock_seconds
                record.failures = 0
                record.first_failure_at = now
            self._records.put(email, record)
            return 0 if record.locked_until > now else self.max_failed - record.failures

    def record_success(self, email: str) -> None:
        with self._lock:
            self._records.remove(email)

    def reset(self) -> None:
        with self._lock:
            self._records.clear()


def get_login_attempt_tracker() -> LoginAttemptTracker:
    return LoginAttemptTracker()
