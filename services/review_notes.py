"""The staff's notes on possible problems (migration 0018), with their author's name and role."""

from __future__ import annotations

from sqlalchemy.orm import Session

from models import RecommendationNote, User
from schemas import NoteOut


def notes_of(db: Session, recommendation_ids: list[str]) -> dict[str, list[NoteOut]]:
    """The notes of these problems with their author's name and role, oldest first."""
    notes: dict[str, list[NoteOut]] = {}
    if not recommendation_ids:
        return notes
    rows = (db.query(RecommendationNote, User)
              .outerjoin(User, User.id == RecommendationNote.author_id)
              .filter(RecommendationNote.recommendation_id.in_(recommendation_ids))
              .order_by(RecommendationNote.created_at, RecommendationNote.id).all())
    for note, author in rows:
        notes.setdefault(note.recommendation_id, []).append(NoteOut(
            id=note.id, recommendation_id=note.recommendation_id, author_id=note.author_id,
            author_name=f"{author.first_name} {author.last_name}" if author else None,
            author_role=author.role if author else None, text=note.text,
            created_at=note.created_at, updated_at=note.updated_at))
    return notes
