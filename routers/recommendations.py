"""AI recommendations: list, human review (review / confirm / dismiss), the staff's notes and the
review inbox (everything of the team still waiting for a person).

The notes (migration 0018) are what a person reads in a possible problem: signed, oldest first, and
announced in the team's bell. Anyone of the team who can review can write one; only its author or
the coach can delete it.
"""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from database import get_db
from errors import AppError
from dependencies import AccessLevel, get_current_user, load_match, load_recommendation, load_team
from models import (
    AIRecommendation, Match, RecommendationIndicator, RecommendationNote, RecommendationStatus, TacticalIndicator, User,
    UserRole,
)
from schemas import (
    InboxProblem, InboxStrength, NoteCreate, NoteOut, RecommendationOut, RecommendationStatusUpdate, ReviewInboxOut,
    StrengthOut,
)
from services.analysis_events import RECOMMENDATION_NOTE, AnalysisEvent, NotificationCenter
from services.review_inbox import inbox_matches, open_problems, unreviewed_strengths
from services.review_notes import notes_of
from services.review_priority import OPEN_STATES, by_priority, review_queue

router = APIRouter(prefix="/api", tags=["AI Recommendations"])

TRANSITIONS = {
    "review": ({RecommendationStatus.GENERATED}, RecommendationStatus.REVIEWED),
    "confirm": ({RecommendationStatus.GENERATED, RecommendationStatus.REVIEWED}, RecommendationStatus.CONFIRMED),
    "dismiss": ({RecommendationStatus.GENERATED, RecommendationStatus.REVIEWED}, RecommendationStatus.DISMISSED),
}


def analysis_of(db: Session, recommendation_id: str) -> str | None:
    return (db.query(TacticalIndicator.video_analysis_id)
              .join(RecommendationIndicator, RecommendationIndicator.indicator_id == TacticalIndicator.id)
              .filter(RecommendationIndicator.recommendation_id == recommendation_id).limit(1).scalar())


def _with_indicator_names(db: Session, recommendations: list[AIRecommendation]) -> list[RecommendationOut]:
    ids = [r.id for r in recommendations]
    notes = notes_of(db, ids)
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
        item.notes = notes.get(recommendation.id, [])
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


@router.post("/recommendations/{recommendation_id}/notes", response_model=NoteOut,
             status_code=status.HTTP_201_CREATED)
def add_note(recommendation_id: str, body: NoteCreate, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    recommendation = load_recommendation(db, recommendation_id, user, AccessLevel.CONTRIBUTE)
    note = RecommendationNote(recommendation_id=recommendation.id, author_id=user.id, text=body.text)
    db.add(note)
    db.commit()
    match = db.get(Match, recommendation.match_id)
    title = recommendation.title.removeprefix("Posible problema táctico: ")
    preview = body.text if len(body.text) <= 120 else body.text[:119] + "…"
    NotificationCenter().publish(AnalysisEvent(
        RECOMMENDATION_NOTE, match.team_id, analysis_of(db, recommendation.id),
        f"{user.first_name} {user.last_name} escribió sobre «{title}» (vs {match.opponent}): {preview}",
        actor_id=user.id))
    return notes_of(db, [recommendation.id])[recommendation.id][-1]


@router.delete("/recommendation-notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    note = db.get(RecommendationNote, note_id)
    if note is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Note not found.")
    load_recommendation(db, note.recommendation_id, user, AccessLevel.READ, label="Note")
    if note.author_id != user.id and user.role != UserRole.COACH:
        raise AppError(status.HTTP_403_FORBIDDEN, "NOTE_NOT_YOURS", "Only its author or the coach can delete a note.")
    db.delete(note)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.get("/teams/{team_id}/review-inbox", response_model=ReviewInboxOut)
def review_inbox(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Open problems (most urgent first, from the heap) and unreviewed strengths of our team, with the
    match and analysis each one comes from. Reviewing is done with the usual PATCH endpoints."""
    load_team(db, team_id, user, AccessLevel.READ)
    problems, rival_problems = open_problems(db, team_id)
    strengths = unreviewed_strengths(db, team_id)
    shown = _with_indicator_names(db, [recommendation for recommendation, _ in problems])
    return ReviewInboxOut(
        problems=[InboxProblem(**item.model_dump(), context=context) for item, (_, context) in zip(shown, problems)],
        strengths=[InboxStrength.model_validate({**StrengthOut.model_validate(strength).model_dump(), "context": context})
                   for strength, context in strengths],
        matches=inbox_matches(problems, strengths), rival_problems=rival_problems)
