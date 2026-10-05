"""Observer pattern: analysis status changes and new tactical alerts.

The Facade publishes events; it does not know who listens. Observers:
- LoggingObserver: audit trail in the server log.
- TeamNotificationInbox: keeps the last notifications per team, read by
  GET /api/notifications (polled by the dashboard).
New observers (e-mail, websockets...) can be added without touching the Facade.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field

from models import utc_now
from singleton import SingletonMeta

logger = logging.getLogger("tactivision.events")

ANALYSIS_QUEUED = "ANALYSIS_QUEUED"
ANALYSIS_STARTED = "ANALYSIS_STARTED"
ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
ANALYSIS_FAILED = "ANALYSIS_FAILED"
ANALYSIS_CANCELLED = "ANALYSIS_CANCELLED"
TACTICAL_ALERT = "TACTICAL_ALERT"


@dataclass(frozen=True)
class AnalysisEvent:
    event: str
    team_id: str
    analysis_id: str
    message: str
    created_at: object = field(default_factory=utc_now)


class AnalysisObserver(ABC):
    @abstractmethod
    def update(self, event: AnalysisEvent) -> None:
        ...


class LoggingObserver(AnalysisObserver):
    def update(self, event: AnalysisEvent) -> None:
        logger.info("[%s] team=%s analysis=%s %s", event.event, event.team_id, event.analysis_id, event.message)


class TeamNotificationInbox(AnalysisObserver, metaclass=SingletonMeta):
    """In-memory, per process. Notifications are lost on restart (acceptable for the prototype)."""

    MAX_PER_TEAM = 50

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_team: dict[str, deque[AnalysisEvent]] = defaultdict(lambda: deque(maxlen=self.MAX_PER_TEAM))

    def update(self, event: AnalysisEvent) -> None:
        with self._lock:
            self._by_team[event.team_id].appendleft(event)

    def for_team(self, team_id: str) -> list[AnalysisEvent]:
        with self._lock:
            return list(self._by_team.get(team_id, []))


class NotificationCenter(metaclass=SingletonMeta):
    """Subject. A Singleton so every part of the app publishes to the same observers."""

    def __init__(self) -> None:
        self._observers: list[AnalysisObserver] = []
        self._lock = threading.Lock()
        self.subscribe(LoggingObserver())
        self.subscribe(TeamNotificationInbox())

    def subscribe(self, observer: AnalysisObserver) -> None:
        with self._lock:
            if observer not in self._observers:
                self._observers.append(observer)

    def unsubscribe(self, observer: AnalysisObserver) -> None:
        with self._lock:
            if observer in self._observers:
                self._observers.remove(observer)

    def publish(self, event: AnalysisEvent) -> None:
        with self._lock:
            observers = list(self._observers)
        for observer in observers:
            try:
                observer.update(event)
            except Exception:  # an observer must never break the analysis
                logger.exception("Observer %s failed", type(observer).__name__)
