"""AI recommendations: list and human review (review / confirm / dismiss)."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from database import get_db
from errors import AppError
from dependencies import AccessLevel, get_current_user, load_match, load_recommendation, load_team
from models import AIRecommendation, Match, RecommendationIndicator, RecommendationStatus, TacticalIndicator, User
from schemas import RecommendationOut, RecommendationStatusUpdate
from services.review_priority import OPEN_STATES, by_priority, review_queue

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
                         .distinct().all())
    return _with_indicator_names(db, by_priority(recommendations))  # most urgent first (heap)


@router.get("/matches/{match_id}/recommendations", response_model=list[RecommendationOut])
def list_match_recommendations(match_id: str, include_dismissed: bool = False, user: User = Depends(get_current_user),
                               db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.READ)
    query = db.query(AIRecommendation).filter(AIRecommendation.match_id == match_id)
    if not include_dismissed:
        query = query.filter(AIRecommendation.status != RecommendationStatus.DISMISSED)
    return _with_indicator_names(db, by_priority(query.all()))


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
    rows = (db.query(Match, AIRecommendation)
              .join(AIRecommendation, AIRecommendation.match_id == Match.id)
              .filter(Match.team_id == team_id, AIRecommendation.status.in_(OPEN_STATES))
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


HEAP_PREVIEW = 15  # nodes of the heap sent to draw the tree (4 levels)


@router.get("/teams/{team_id}/review-queue")
def team_review_queue(team_id: str, limit: int = Query(default=5, ge=1, le=20),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The most urgent open issues of the whole team, taken from a priority queue (binary heap).

    ``items`` are the first ``limit`` popped from the heap (rank 1 = review first); ``heap`` is the
    array as stored, level by level, so the app can draw the tree."""
    load_team(db, team_id, user, AccessLevel.READ)
    rows = (db.query(AIRecommendation, Match).join(Match, Match.id == AIRecommendation.match_id)
              .filter(Match.team_id == team_id, AIRecommendation.status.in_(OPEN_STATES)).all())
    match_of = {recommendation: match for recommendation, match in rows}
    top, heap, total = review_queue(match_of, limit)
    shown = {item.id for item in top} | {item.id for item in heap[:HEAP_PREVIEW]}
    analysis_of = dict(
        db.query(RecommendationIndicator.recommendation_id, TacticalIndicator.video_analysis_id)
          .join(TacticalIndicator, TacticalIndicator.id == RecommendationIndicator.indicator_id)
          .filter(RecommendationIndicator.recommendation_id.in_(shown)).all()
    ) if shown else {}

    def view(recommendation: AIRecommendation, rank: int | None = None) -> dict:
        match = match_of[recommendation]
        return {"id": recommendation.id, "rank": rank, "title": recommendation.title,
                "severity": recommendation.severity, "confidence": float(recommendation.confidence),
                "status": recommendation.status, "match_id": match.id, "opponent": match.opponent,
                "match_date": match.match_date.isoformat(), "analysis_id": analysis_of.get(recommendation.id)}

    return {"total": total,
            "items": [view(item, rank) for rank, item in enumerate(top, start=1)],
            "heap": [view(item) for item in heap[:HEAP_PREVIEW]]}
