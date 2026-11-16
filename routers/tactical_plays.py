"""Tactical design: plays and versions (Prototype + Stack in services.tactical_versions)."""

import json

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from errors import AppError, domain_error
from dependencies import AccessLevel, get_current_user, load_tactical_play, load_team
from models import Match, MatchTacticalPlay, TacticalPlay, TacticalPlayVersion, TeamActionType, User
from schemas import (
    PLAY_DESCRIPTION_MAX, PLAY_NAME_MAX, ActionTypeCreate, ActionTypeOut, MatchOut, TacticalPlayCreate, TacticalPlayOut, TacticalPlaySummaryOut, TacticalPlayUpdate, TacticalPlayVersionCreate,
    TacticalPlayVersionOut,
)
from services.tactical_versions import VersionError, activate_version, create_version, undo_version, versions_of

router = APIRouter(prefix="/api", tags=["Tactical Design"])


def version_out(version: TacticalPlayVersion) -> TacticalPlayVersionOut:
    return TacticalPlayVersionOut(
        id=version.id, tactical_play_id=version.tactical_play_id, created_by=version.created_by,
        version_number=version.version_number, configuration=json.loads(version.configuration_data),
        created_at=version.created_at, is_current=version.is_current,
    )


@router.get("/teams/{team_id}/tactical-plays", response_model=list[TacticalPlaySummaryOut])
def list_plays(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.READ)
    plays = db.query(TacticalPlay).filter(TacticalPlay.team_id == team_id).all()
    versions = (db.query(TacticalPlayVersion)
                  .filter(TacticalPlayVersion.tactical_play_id.in_([play.id for play in plays]))
                  .all()) if plays else []
    by_play: dict[str, list[TacticalPlayVersion]] = {}
    for version in versions:
        by_play.setdefault(version.tactical_play_id, []).append(version)

    summaries = []
    for play in plays:
        own = by_play.get(play.id, [])
        current = next((v for v in own if v.is_current), None)
        summaries.append(TacticalPlaySummaryOut(
            id=play.id, team_id=play.team_id, name=play.name, description=play.description,
            action_type=play.action_type, created_at=play.created_at, is_reusable=play.is_reusable,
            version_count=len(own), current_version_number=current.version_number if current else None,
            updated_at=max((v.created_at for v in own), default=None),
            configuration=json.loads(current.configuration_data) if current else {},
        ))
    return sorted(summaries, key=lambda item: item.updated_at or item.created_at, reverse=True)


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


@router.put("/tactical-plays/{play_id}", response_model=TacticalPlayOut)
def update_play(play_id: str, body: TacticalPlayUpdate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    play = load_tactical_play(db, play_id, user, AccessLevel.MANAGE)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        del changes["name"]          # a play always has a name
    for field, value in changes.items():
        setattr(play, field, value)
    # A play saved before the limits may be longer: any change to it has to bring it within them.
    if len(play.name) > PLAY_NAME_MAX or len(play.description or "") > PLAY_DESCRIPTION_MAX:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "PLAY_TEXT_TOO_LONG",
                       f"Name up to {PLAY_NAME_MAX} characters and description up to {PLAY_DESCRIPTION_MAX}.",
                       name_max=PLAY_NAME_MAX, description_max=PLAY_DESCRIPTION_MAX)
    db.commit()
    return play


# ------------------------------------------------------------------ action types written by the team
@router.get("/teams/{team_id}/action-types", response_model=list[ActionTypeOut])
def list_action_types(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The action types this team wrote, besides the fixed ones the editor offers."""
    load_team(db, team_id, user, AccessLevel.READ)
    return db.query(TeamActionType).filter(TeamActionType.team_id == team_id).order_by(func.lower(TeamActionType.name)).all()


@router.post("/teams/{team_id}/action-types", response_model=ActionTypeOut, status_code=status.HTTP_201_CREATED)
def add_action_type(team_id: str, body: ActionTypeCreate, response: Response, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Saves a new action type. Writing one that already exists (in any case) returns that one."""
    load_team(db, team_id, user, AccessLevel.MANAGE)
    existing = (db.query(TeamActionType)
                  .filter(TeamActionType.team_id == team_id, func.lower(TeamActionType.name) == body.name.lower()).first())
    if existing:
        response.status_code = status.HTTP_200_OK
        return existing
    entity = TeamActionType(team_id=team_id, name=body.name, created_by=user.id)
    db.add(entity)
    db.commit()
    return entity


@router.delete("/teams/{team_id}/action-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_action_type(team_id: str, type_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Removes a type from the list. The plays that already use it keep their text."""
    load_team(db, team_id, user, AccessLevel.MANAGE)
    entity = db.query(TeamActionType).filter(TeamActionType.id == type_id, TeamActionType.team_id == team_id).first()
    if entity is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Action type not found.")
    db.delete(entity)
    db.commit()


@router.get("/tactical-plays/{play_id}/matches", response_model=list[MatchOut])
def play_matches(play_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Matches where this play is planned to be used."""
    play = load_tactical_play(db, play_id, user, AccessLevel.READ)
    return (db.query(Match).join(MatchTacticalPlay, MatchTacticalPlay.match_id == Match.id)
              .filter(MatchTacticalPlay.tactical_play_id == play.id, Match.team_id == play.team_id)
              .order_by(Match.match_date.desc()).all())


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
        raise domain_error(error, status.HTTP_400_BAD_REQUEST) from error
    db.commit()
    return version_out(version)


@router.post("/tactical-plays/{play_id}/versions/{version_id}/activate", response_model=TacticalPlayVersionOut)
def activate(play_id: str, version_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    play = load_tactical_play(db, play_id, user, AccessLevel.MANAGE)
    try:
        version = activate_version(db, play, version_id)
    except VersionError as error:
        raise domain_error(error, status.HTTP_404_NOT_FOUND) from error
    db.commit()
    return version_out(version)


@router.post("/tactical-plays/{play_id}/versions/undo", response_model=TacticalPlayVersionOut)
def undo(play_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    play = load_tactical_play(db, play_id, user, AccessLevel.MANAGE)
    try:
        version = undo_version(db, play)
    except VersionError as error:
        raise domain_error(error, status.HTTP_409_CONFLICT) from error
    db.commit()
    return version_out(version)
