"""AI recommendations: list and human review (review / confirm / dismiss)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import AccessLevel, get_current_user, load_match, load_recommendation
from models import AIRecommendation, RecommendationIndicator, RecommendationStatus, TacticalIndicator, User
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
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot {body.action} a {recommendation.status} recommendation.")
    recommendation.status = target
    db.commit()
    return _with_indicator_names(db, [recommendation])[0]
