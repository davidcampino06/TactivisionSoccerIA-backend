"""AI recommendations: list and human review (review / confirm / dismiss)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from database import get_db
from errors import AppError
from dependencies import AccessLevel, get_current_user, load_match, load_recommendation, load_team
from models import AIRecommendation, Match, RecommendationIndicator, RecommendationStatus, TacticalIndicator, User
from schemas import RecommendationOut, RecommendationStatusUpdate

router = APIRouter(prefix="/api", tags=["AI Recommendations"])

TRANSITIONS = {
    "review": ({RecommendationStatus.GENERATED}, RecommendationStatus.REVIEWED),
    "confirm": ({RecommendationStatus.GENERATED, RecommendationStatus.REVIEWED}, RecommendationStatus.CONFIRMED),
    "dismiss": ({RecommendationStatus.GENERATED, RecommendationStatus.REVIEWED}, RecommendationStatus.DISMISSED),
}


def _with_indicator_names(db: Session, recommendations: list[AIRecommendation]) -> list[RecommendationOut]:
    ids = [r.id for r in recommendations]
    names: dict[str, list[str]] = {}
    if ids:
        for recommendation_id, name in (db.query(RecommendationIndicator.recommendation_id, TacticalIndicator.name)
                                          .join(TacticalIndicator, TacticalIndicator.id == RecommendationIndicator.indicator_id)
                                          .filter(RecommendationIndicator.recommendation_id.in_(ids)).all()):
            names.setdefault(recommendation_id, []).append(name)
    output = []
    for recommendation in recommendations:
        item = RecommendationOut.model_validate(recommendation)
        item.indicator_names = names.get(recommendation.id, [])
        output.append(item)
    return output


def recommendations_for_analysis(db: Session, analysis_id: str) -> list[RecommendationOut]:
    recommendations = (db.query(AIRecommendation)
                         .join(RecommendationIndicator, RecommendationIndicator.recommendation_id == AIRecommendation.id)
                         .join(TacticalIndicator, TacticalIndicator.id == RecommendationIndicator.indicator_id)
                         .filter(TacticalIndicator.video_analysis_id == analysis_id)
                         .distinct().order_by(AIRecommendation.confidence.desc()).all())
    return _with_indicator_names(db, recommendations)


@router.get("/matches/{match_id}/recommendations", response_model=list[RecommendationOut])
def list_match_recommendations(match_id: str, include_dismissed: bool = False, user: User = Depends(get_current_user),
                               db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.READ)
    query = db.query(AIRecommendation).filter(AIRecommendation.match_id == match_id)
    if not include_dismissed:
        query = query.filter(AIRecommendation.status != RecommendationStatus.DISMISSED)
    return _with_indicator_names(db, query.order_by(AIRecommendation.confidence.desc()).all())


@router.patch("/recommendations/{recommendation_id}", response_model=RecommendationOut)
def review_recommendation(recommendation_id: str, body: RecommendationStatusUpdate,
                          user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    recommendation = load_recommendation(db, recommendation_id, user, AccessLevel.CONTRIBUTE)
    allowed_from, target = TRANSITIONS[body.action]
    if recommendation.status not in allowed_from:
        raise AppError(status.HTTP_409_CONFLICT, "INVALID_RECOMMENDATION_STATE",
                       f"Cannot {body.action} a {recommendation.status} recommendation.")
    recommendation.status = target
    db.commit()
    return _with_indicator_names(db, [recommendation])[0]


@router.get("/teams/{team_id}/pending-reviews")
def pending_reviews(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Possible issues still open (not confirmed or dismissed), grouped by match, newest match first."""
    load_team(db, team_id, user, AccessLevel.READ)
    open_states = (RecommendationStatus.GENERATED, RecommendationStatus.REVIEWED)
    rows = (db.query(Match, AIRecommendation)
              .join(AIRecommendation, AIRecommendation.match_id == Match.id)
              .filter(Match.team_id == team_id, AIRecommendation.status.in_(open_states))
              .order_by(Match.match_date.desc()).all())
    grouped: dict[str, dict] = {}
    for match, recommendation in rows:
        entry = grouped.setdefault(match.id, {"match_id": match.id, "opponent": match.opponent,
                                              "match_date": match.match_date.isoformat(), "open": 0, "high": 0,
                                              "unreviewed": 0})
        entry["open"] += 1
        entry["high"] += recommendation.severity == "HIGH"
        entry["unreviewed"] += recommendation.status == RecommendationStatus.GENERATED
    matches = list(grouped.values())
    return {"total": sum(m["open"] for m in matches), "high": sum(m["high"] for m in matches), "matches": matches}
