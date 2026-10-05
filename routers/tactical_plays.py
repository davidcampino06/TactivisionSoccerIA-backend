"""Tactical design: plays and versions (Prototype + Stack in services.tactical_versions)."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import AccessLevel, get_current_user, load_tactical_play, load_team
from models import TacticalPlay, TacticalPlayVersion, User
from schemas import TacticalPlayCreate, TacticalPlayOut, TacticalPlayVersionCreate, TacticalPlayVersionOut
from services.tactical_versions import VersionError, activate_version, create_version, undo_version, versions_of

router = APIRouter(prefix="/api", tags=["Tactical Design"])


def version_out(version: TacticalPlayVersion) -> TacticalPlayVersionOut:
    return TacticalPlayVersionOut(
        id=version.id, tactical_play_id=version.tactical_play_id, created_by=version.created_by,
        version_number=version.version_number, configuration=json.loads(version.configuration_data),
        created_at=version.created_at, is_current=version.is_current,
    )


@router.get("/teams/{team_id}/tactical-plays", response_model=list[TacticalPlayOut])
def list_plays(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.READ)
    return db.query(TacticalPlay).filter(TacticalPlay.team_id == team_id).order_by(TacticalPlay.created_at.desc()).all()


@router.post("/teams/{team_id}/tactical-plays", response_model=TacticalPlayOut, status_code=status.HTTP_201_CREATED)
def create_play(team_id: str, body: TacticalPlayCreate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.MANAGE)
    play = TacticalPlay(team_id=team_id, **body.model_dump(exclude={"configuration"}))
    db.add(play)
    db.flush()
    create_version(db, play, user, body.configuration, None)
    db.commit()
    return play


@router.get("/tactical-plays/{play_id}", response_model=TacticalPlayOut)
def get_play(play_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_tactical_play(db, play_id, user, AccessLevel.READ)


@router.delete("/tactical-plays/{play_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_play(play_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(load_tactical_play(db, play_id, user, AccessLevel.MANAGE))
    db.commit()


@router.get("/tactical-plays/{play_id}/versions", response_model=list[TacticalPlayVersionOut])
def list_versions(play_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    play = load_tactical_play(db, play_id, user, AccessLevel.READ)
    return [version_out(v) for v in versions_of(db, play)]


@router.post("/tactical-plays/{play_id}/versions", response_model=TacticalPlayVersionOut,
             status_code=status.HTTP_201_CREATED)
def new_version(play_id: str, body: TacticalPlayVersionCreate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    play = load_tactical_play(db, play_id, user, AccessLevel.MANAGE)
    try:
        version = create_version(db, play, user, body.configuration, body.base_version_id)
    except VersionError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    db.commit()
    return version_out(version)


@router.post("/tactical-plays/{play_id}/versions/{version_id}/activate", response_model=TacticalPlayVersionOut)
def activate(play_id: str, version_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    play = load_tactical_play(db, play_id, user, AccessLevel.MANAGE)
    try:
        version = activate_version(db, play, version_id)
    except VersionError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    db.commit()
    return version_out(version)


@router.post("/tactical-plays/{play_id}/versions/undo", response_model=TacticalPlayVersionOut)
def undo(play_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    play = load_tactical_play(db, play_id, user, AccessLevel.MANAGE)
    try:
        version = undo_version(db, play)
    except VersionError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    db.commit()
    return version_out(version)
