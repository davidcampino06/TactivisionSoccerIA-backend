"""Matches, match events, formations used and tactical plays included."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from database import get_db
from errors import AppError
from dependencies import AccessLevel, get_current_user, load_match, load_tactical_play, load_team
from models import Formation, Match, MatchEvent, MatchFormation, MatchTacticalPlay, TacticalPlay, User
from schemas import (
    FormationOut, MatchCreate, MatchEventCreate, MatchEventOut, MatchFormationRequest, MatchNeighborsOut, MatchOut,
    MatchResultUpdate, MatchTacticalPlayRequest, MatchUpdate, TacticalPlayOut,
)
from services.match_timeline import MatchTimeline

router = APIRouter(prefix="/api", tags=["Matches"])


@router.get("/teams/{team_id}/matches", response_model=list[MatchOut])
def list_matches(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.READ)
    return db.query(Match).filter(Match.team_id == team_id).order_by(Match.match_date.desc()).all()


@router.post("/teams/{team_id}/matches", response_model=MatchOut, status_code=status.HTTP_201_CREATED)
def create_match(team_id: str, body: MatchCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.CONTRIBUTE)
    match = Match(team_id=team_id, **body.model_dump())
    db.add(match)
    db.commit()
    return match


@router.get("/matches/{match_id}", response_model=MatchOut)
def get_match(match_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_match(db, match_id, user, AccessLevel.READ)


@router.put("/matches/{match_id}", response_model=MatchOut)
def update_match(match_id: str, body: MatchUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    match = load_match(db, match_id, user, AccessLevel.CONTRIBUTE)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(match, field, value)
    db.commit()
    return match


@router.put("/matches/{match_id}/result", response_model=MatchOut)
def update_result(match_id: str, body: MatchResultUpdate, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    match = load_match(db, match_id, user, AccessLevel.CONTRIBUTE)
    match.home_score, match.away_score = body.home_score, body.away_score
    own, rival = (body.home_score, body.away_score) if match.is_home else (body.away_score, body.home_score)
    match.result = "WIN" if own > rival else "LOSS" if own < rival else "DRAW"
    match.status = "PLAYED"
    db.commit()
    return match


@router.delete("/matches/{match_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_match(match_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(load_match(db, match_id, user, AccessLevel.MANAGE))
    db.commit()


@router.get("/matches/{match_id}/neighbors", response_model=MatchNeighborsOut)
def match_neighbors(match_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Previous / next match using the doubly linked match timeline."""
    match = load_match(db, match_id, user, AccessLevel.READ)
    previous, following = MatchTimeline.for_team(db, match.team_id).neighbors(match.id)
    return {"previous": previous, "current": match, "next": following}


# ------------------------------------------------------------------- events
@router.get("/matches/{match_id}/events", response_model=list[MatchEventOut])
def list_events(match_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.READ)
    return (db.query(MatchEvent).filter(MatchEvent.match_id == match_id)
              .order_by(MatchEvent.minute, MatchEvent.second).all())


@router.post("/matches/{match_id}/events", response_model=MatchEventOut, status_code=status.HTTP_201_CREATED)
def register_event(match_id: str, body: MatchEventCreate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.CONTRIBUTE)
    event = MatchEvent(match_id=match_id, **body.model_dump())
    db.add(event)
    db.commit()
    return event


@router.put("/matches/{match_id}/events/{event_id}", response_model=MatchEventOut)
def update_event(match_id: str, event_id: str, body: MatchEventCreate, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.CONTRIBUTE)
    event = db.get(MatchEvent, event_id)
    if event is None or event.match_id != match_id:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Event not found.")
    for field, value in body.model_dump().items():
        setattr(event, field, value)
    db.commit()
    return event


@router.delete("/matches/{match_id}/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(match_id: str, event_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.CONTRIBUTE)
    event = db.get(MatchEvent, event_id)
    if event is None or event.match_id != match_id:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Event not found.")
    db.delete(event)
    db.commit()


# ------------------------------------------------------- formations / plays
@router.get("/matches/{match_id}/formations", response_model=list[FormationOut])
def match_formations(match_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.READ)
    return (db.query(Formation).join(MatchFormation, MatchFormation.formation_id == Formation.id)
              .filter(MatchFormation.match_id == match_id).all())


@router.post("/matches/{match_id}/formations", status_code=status.HTTP_204_NO_CONTENT)
def add_match_formation(match_id: str, body: MatchFormationRequest, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.CONTRIBUTE)
    if db.get(Formation, body.formation_id) is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Formation not found.")
    exists = db.query(MatchFormation).filter_by(match_id=match_id, formation_id=body.formation_id).first()
    if not exists:
        db.add(MatchFormation(match_id=match_id, formation_id=body.formation_id))
        db.commit()


@router.get("/matches/{match_id}/tactical-plays", response_model=list[TacticalPlayOut])
def match_tactical_plays(match_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.READ)
    return (db.query(TacticalPlay).join(MatchTacticalPlay, MatchTacticalPlay.tactical_play_id == TacticalPlay.id)
              .filter(MatchTacticalPlay.match_id == match_id).all())


@router.post("/matches/{match_id}/tactical-plays", status_code=status.HTTP_204_NO_CONTENT)
def add_match_tactical_play(match_id: str, body: MatchTacticalPlayRequest, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    match = load_match(db, match_id, user, AccessLevel.CONTRIBUTE)
    play = load_tactical_play(db, body.tactical_play_id, user, AccessLevel.READ)
    if play.team_id != match.team_id:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Tactical play belongs to another team.")
    if not db.query(MatchTacticalPlay).filter_by(match_id=match_id, tactical_play_id=play.id).first():
        db.add(MatchTacticalPlay(match_id=match_id, tactical_play_id=play.id))
        db.commit()


@router.delete("/matches/{match_id}/tactical-plays/{play_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_match_tactical_play(match_id: str, play_id: str, user: User = Depends(get_current_user),
                               db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.CONTRIBUTE)
    link = db.query(MatchTacticalPlay).filter_by(match_id=match_id, tactical_play_id=play_id).first()
    if link is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "The play is not linked to this match.")
    db.delete(link)
    db.commit()
