"""Singleton pattern (thread-safe metaclass).

Used only for objects that MUST exist once per process:
- AnalysisJobQueue: one FIFO queue and one worker; two instances would run analyses in parallel
  and overload the AI Service.
- NotificationCenter: one event bus so every observer sees every analysis event.
"""

import threading
from abc import ABCMeta


class SingletonMeta(ABCMeta):
    """Inherits ABCMeta so singletons can also implement abstract interfaces (e.g. observers)."""

    _instances: dict[type, object] = {}
    _lock = threading.RLock()  # re-entrant: a singleton may create another singleton in __init__

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

    @classmethod
    def reset(mcs, cls: type) -> None:
        """Testing helper."""
        with mcs._lock:
            mcs._instances.pop(cls, None)
