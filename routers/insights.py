"""Tactical analysis across matches (compare, evolution) and notifications."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import AccessLevel, get_current_user, load_team
from models import Team, User, UserRole
from schemas import NotificationOut
from services.analysis_events import TeamNotificationInbox
from services.match_timeline import ComparisonError, compare_matches, team_evolution

router = APIRouter(prefix="/api", tags=["Tactical Analysis"])


@router.get("/teams/{team_id}/comparisons")
def compare(team_id: str, match_ids: list[str] = Query(...), user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.READ)
    try:
        return compare_matches(db, team_id, match_ids)
    except ComparisonError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error


@router.get("/teams/{team_id}/evolution")
def evolution(team_id: str, match_ids: list[str] | None = Query(default=None), last: int = Query(default=5, ge=3, le=20),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.READ)
    try:
        return team_evolution(db, team_id, match_ids, last)
    except ComparisonError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == UserRole.ADMINISTRATOR:
        return []
    team_id = user.team_id
    if user.role == UserRole.COACH:
        team = db.query(Team).filter(Team.coach_id == user.id).first()
        team_id = team.id if team else None
    if not team_id:
        return []
    return [vars(event) for event in TeamNotificationInbox().for_team(team_id)]
