"""Tactical analysis across matches (compare, evolution)."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from database import get_db
from errors import domain_error
from dependencies import AccessLevel, get_current_user, load_team
from models import User
from services.match_timeline import ComparisonError, analysed_matches, compare_matches, team_evolution

router = APIRouter(prefix="/api", tags=["Tactical Analysis"])


@router.get("/teams/{team_id}/analysed-matches")
def list_analysed_matches(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Matches that already have a completed analysis (the ones that can be compared), newest first."""
    load_team(db, team_id, user, AccessLevel.READ)
    return analysed_matches(db, team_id)


@router.get("/teams/{team_id}/comparisons")
def compare(team_id: str, match_ids: list[str] = Query(...), user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.READ)
    try:
        return compare_matches(db, team_id, match_ids)
    except ComparisonError as error:
        raise domain_error(error, status.HTTP_400_BAD_REQUEST) from error


@router.get("/teams/{team_id}/evolution")
def evolution(team_id: str, match_ids: list[str] | None = Query(default=None), last: int = Query(default=5, ge=3, le=20),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.READ)
    try:
        return team_evolution(db, team_id, match_ids, last)
    except ComparisonError as error:
        raise domain_error(error, status.HTTP_400_BAD_REQUEST) from error
