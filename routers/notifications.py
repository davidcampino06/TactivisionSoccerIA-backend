"""Notifications of the signed-in user's team (the bell).

Notifications are shared by the team; whether each one was read is personal (notification_reads),
and so is deleting one: it disappears from that user's bell only (hidden_at, migration 0014).
The administrator has no team, so his list is always empty. Row-Level Security filters the
tables again in PostgreSQL (TactiSoccerIA-db migration 0004).
"""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from errors import AppError
from models import Notification, NotificationRead, Team, User, UserRole, utc_now
from schemas import NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


def _team_id(db: Session, user: User) -> str | None:
    if user.role == UserRole.ADMINISTRATOR:
        return None
    if user.role == UserRole.COACH:
        return db.query(Team.id).filter(Team.coach_id == user.id).scalar()
    return user.team_id


def _read_by(user: User):
    return exists().where(NotificationRead.notification_id == Notification.id, NotificationRead.user_id == user.id)


def _hidden_by(user: User):
    return exists().where(NotificationRead.notification_id == Notification.id, NotificationRead.user_id == user.id,
                          NotificationRead.hidden_at.is_not(None))


def _hide(db: Session, notification_id: str, user: User) -> bool:
    """Hides one notification for this user (and marks it read). False if it was already hidden."""
    mark = db.get(NotificationRead, (notification_id, user.id))
    now = utc_now()
    if mark is None:
        db.add(NotificationRead(notification_id=notification_id, user_id=user.id, read_at=now, hidden_at=now))
        return True
    if mark.hidden_at is None:
        mark.hidden_at = now
        return True
    return False


@router.get("", response_model=list[NotificationOut])
def list_notifications(limit: int = Query(default=30, ge=1, le=100), unread_only: bool = False,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Newest first, each with ``read`` for the current user."""
    team_id = _team_id(db, user)
    if not team_id:
        return []
    read = _read_by(user)
    query = db.query(Notification, read.label("read")).filter(Notification.team_id == team_id, ~_hidden_by(user))
    if unread_only:
        query = query.filter(~read)
    rows = query.order_by(Notification.created_at.desc()).limit(limit).all()
    return [NotificationOut.model_validate(notification).model_copy(update={"read": is_read})
            for notification, is_read in rows]


@router.get("/unread-count")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Small and cheap: the app asks for it every few seconds to update the badge."""
    team_id = _team_id(db, user)
    if not team_id:
        return {"unread": 0}
    count = db.query(Notification.id).filter(Notification.team_id == team_id, ~_read_by(user)).count()
    return {"unread": count}


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(notification_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    team_id = _team_id(db, user)
    notification = db.get(Notification, notification_id)
    if notification is None or notification.team_id != team_id:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Notification not found.")
    if not db.get(NotificationRead, (notification_id, user.id)):
        db.add(NotificationRead(notification_id=notification_id, user_id=user.id))
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    team_id = _team_id(db, user)
    if not team_id:
        return {"marked": 0}
    pending = db.scalars(select(Notification.id).where(Notification.team_id == team_id, ~_read_by(user))).all()
    db.add_all(NotificationRead(notification_id=notification_id, user_id=user.id) for notification_id in pending)
    db.commit()
    return {"marked": len(pending)}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(notification_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Deletes it from this user's bell; teammates keep it. Deleting it again is harmless."""
    team_id = _team_id(db, user)
    notification = db.get(Notification, notification_id)
    if notification is None or notification.team_id != team_id:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Notification not found.")
    if _hide(db, notification_id, user):
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("")
def delete_all_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Empties this user's bell (the team's notifications stay for everybody else)."""
    team_id = _team_id(db, user)
    if not team_id:
        return {"deleted": 0}
    visible = db.scalars(select(Notification.id).where(Notification.team_id == team_id, ~_hidden_by(user))).all()
    deleted = sum(_hide(db, notification_id, user) for notification_id in visible)
    db.commit()
    return {"deleted": deleted}
