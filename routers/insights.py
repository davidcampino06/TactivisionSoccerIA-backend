"""Tactical analysis across matches (compare, evolution, follow-up of the confirmed problems)."""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from database import get_db
from errors import domain_error
from dependencies import AccessLevel, get_current_user, load_team
from models import User
from services.comparison_pdf import comparison_pdf
from services.match_timeline import ComparisonError, analysed_matches, compare_matches, team_evolution
from services.problem_tracking import problem_tracking
from services.team_crest import crest_bytes

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


@router.get("/teams/{team_id}/comparisons/pdf", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
def compare_pdf(team_id: str, match_ids: list[str] = Query(...), user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """The comparison of the chosen matches as a PDF: the matches, a chart of the differences between
    the first and the last one, and a bar chart per indicator. Same numbers as the comparison page."""
    team = load_team(db, team_id, user, AccessLevel.READ)
    try:
        comparison = compare_matches(db, team_id, match_ids)
    except ComparisonError as error:
        raise domain_error(error, status.HTTP_400_BAD_REQUEST) from error
    return Response(comparison_pdf(team.name, comparison, crest_bytes(db, team_id)), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="comparacion-de-partidos.pdf"'})


@router.get("/teams/{team_id}/evolution")
def evolution(team_id: str, match_ids: list[str] | None = Query(default=None), last: int = Query(default=5, ge=3, le=20),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.READ)
    try:
        return team_evolution(db, team_id, match_ids, last)
    except ComparisonError as error:
        raise domain_error(error, status.HTTP_400_BAD_REQUEST) from error


@router.get("/teams/{team_id}/problem-tracking")
def confirmed_problem_tracking(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Each problem of our team confirmed by a person and whether it came back in the matches analysed after."""
    load_team(db, team_id, user, AccessLevel.READ)
    return problem_tracking(db, team_id)
