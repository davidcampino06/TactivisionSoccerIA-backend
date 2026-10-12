"""Observer pattern: analysis status changes, tactical alerts and other team events.

The Facade (and the teams router) publish events; they do not know who listens. Observers:
- LoggingObserver: audit trail in the server log (every event).
- PersistentNotificationObserver: stores the events people must see in the bell
  (table ``notifications``, TactiSoccerIA-db migration 0004), so they survive a restart.
New observers (e-mail, websockets...) can be added without touching the publishers.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import database
import rls
from models import Notification, NotificationRead, Video, VideoAnalysis, utc_now
from singleton import SingletonMeta

logger = logging.getLogger("tactivision.events")

ANALYSIS_QUEUED = "ANALYSIS_QUEUED"
ANALYSIS_STARTED = "ANALYSIS_STARTED"
ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
ANALYSIS_FAILED = "ANALYSIS_FAILED"
ANALYSIS_CANCELLED = "ANALYSIS_CANCELLED"
TACTICAL_ALERT = "TACTICAL_ALERT"
ANALYST_JOINED = "ANALYST_JOINED"


@dataclass(frozen=True)
class AnalysisEvent:
    event: str
    team_id: str
    analysis_id: str | None
    message: str
    created_at: object = field(default_factory=utc_now)
    # Who caused the event: it is stored as already read for that user (he does not need the alert).
    actor_id: str | None = None


class AnalysisObserver(ABC):
    @abstractmethod
    def update(self, event: AnalysisEvent) -> None:
        ...


class LoggingObserver(AnalysisObserver):
    def update(self, event: AnalysisEvent) -> None:
        logger.info("[%s] team=%s analysis=%s %s", event.event, event.team_id, event.analysis_id, event.message)


class PersistentNotificationObserver(AnalysisObserver):
    """Saves the events worth a notification. "Queued" and "started" are only logged: the analysis
    screen already shows them live, and in the bell they would bury the important ones."""

    STORED_EVENTS = frozenset({ANALYSIS_COMPLETED, ANALYSIS_FAILED, ANALYSIS_CANCELLED, TACTICAL_ALERT, ANALYST_JOINED})
    KEEP_PER_TEAM = 100  # older ones are deleted so the table does not grow forever

    def update(self, event: AnalysisEvent) -> None:
        if event.event not in self.STORED_EVENTS:
            return
        # Own session: the event may come from the background worker or after a request committed.
        with rls.mark_system(database.SessionLocal()) as db:
            match_id = None
            if event.analysis_id:
                match_id = (db.query(Video.match_id).join(VideoAnalysis, VideoAnalysis.video_id == Video.id)
                              .filter(VideoAnalysis.id == event.analysis_id).scalar())
            notification = Notification(team_id=event.team_id, event=event.event, analysis_id=event.analysis_id,
                                        match_id=match_id, message=event.message[:500], created_at=event.created_at)
            db.add(notification)
            db.flush()
            if event.actor_id:
                db.add(NotificationRead(notification_id=notification.id, user_id=event.actor_id))
            stale = [row.id for row in db.query(Notification.id).filter(Notification.team_id == event.team_id)
                     .order_by(Notification.created_at.desc()).offset(self.KEEP_PER_TEAM).all()]
            if stale:
                db.query(Notification).filter(Notification.id.in_(stale)).delete(synchronize_session=False)
            db.commit()


class NotificationCenter(metaclass=SingletonMeta):
    """Subject. A Singleton so every part of the app publishes to the same observers."""

    def __init__(self) -> None:
        self._observers: list[AnalysisObserver] = []
        self._lock = threading.Lock()
        self.subscribe(LoggingObserver())
        self.subscribe(PersistentNotificationObserver())

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
