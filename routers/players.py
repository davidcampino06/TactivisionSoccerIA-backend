"""Players and player-team history."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from errors import AppError
from dependencies import AccessLevel, get_current_user, load_player, load_team
from models import Detection, Match, Player, PlayerTeamHistory, User, Video, VideoAnalysis, utc_now
from schemas import (
    PlayerAppearanceOut, PlayerCreate, PlayerHistoryOut, PlayerOut, PlayerRemoveRequest, PlayerUpdate,
)

router = APIRouter(prefix="/api", tags=["Players"])


def _ensure_shirt_available(db: Session, team_id: str, shirt_number: int | None, exclude_id: str | None = None):
    if shirt_number is None:
        return
    query = db.query(Player).filter(Player.team_id == team_id, Player.shirt_number == shirt_number,
                                    Player.status != "INACTIVE")
    if exclude_id:
        query = query.filter(Player.id != exclude_id)
    if query.first():
        raise AppError(status.HTTP_409_CONFLICT, "SHIRT_NUMBER_TAKEN", f"Shirt number {shirt_number} is already in use.",
                       shirt_number=shirt_number)


def _open_history(db: Session, player: Player) -> None:
    db.add(PlayerTeamHistory(player_id=player.id, team_id=player.team_id))


def _close_history(db: Session, player: Player, reason: str) -> None:
    entry = (db.query(PlayerTeamHistory)
               .filter(PlayerTeamHistory.player_id == player.id, PlayerTeamHistory.left_at.is_(None)).first())
    if entry:
        entry.left_at = utc_now()
        entry.withdrawal_reason = reason


@router.get("/teams/{team_id}/players", response_model=list[PlayerOut])
def list_players(team_id: str, include_inactive: bool = False, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.READ)
    query = db.query(Player).filter(Player.team_id == team_id)
    if not include_inactive:
        query = query.filter(Player.status != "INACTIVE")
    return query.order_by(Player.shirt_number.nulls_last(), Player.last_name).all()


@router.post("/teams/{team_id}/players", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
def add_player(team_id: str, body: PlayerCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.MANAGE)
    _ensure_shirt_available(db, team_id, body.shirt_number)
    player = Player(team_id=team_id, **body.model_dump())
    db.add(player)
    db.flush()
    _open_history(db, player)
    db.commit()
    return player


@router.get("/players/{player_id}", response_model=PlayerOut)
def get_player(player_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_player(db, player_id, user, AccessLevel.READ)


@router.put("/players/{player_id}", response_model=PlayerOut)
def update_player(player_id: str, body: PlayerUpdate, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    player = load_player(db, player_id, user, AccessLevel.MANAGE)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("status") == "INACTIVE" and player.status != "INACTIVE":
        # Leaving the squad needs a reason for the history: use DELETE /players/{id}.
        raise AppError(status.HTTP_409_CONFLICT, "PLAYER_REMOVE_REQUIRES_REASON",
                       "Use the remove endpoint, which records the withdrawal reason.")
    reactivating = player.status == "INACTIVE" and changes.get("status") not in (None, "INACTIVE")
    if "shirt_number" in changes or reactivating:
        _ensure_shirt_available(db, player.team_id, changes.get("shirt_number", player.shirt_number),
                                exclude_id=player.id)
    for field, value in changes.items():
        setattr(player, field, value)
    if reactivating:
        _open_history(db, player)
    db.commit()
    return player


@router.delete("/players/{player_id}", response_model=PlayerOut)
def remove_player(player_id: str, body: PlayerRemoveRequest, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Removes the player from the active squad; history and past detections are preserved."""
    player = load_player(db, player_id, user, AccessLevel.MANAGE)
    player.status = "INACTIVE"
    _close_history(db, player, body.withdrawal_reason)
    db.commit()
    return player


@router.get("/players/{player_id}/history", response_model=list[PlayerHistoryOut])
def player_history(player_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_player(db, player_id, user, AccessLevel.READ)
    return (db.query(PlayerTeamHistory).filter(PlayerTeamHistory.player_id == player_id)
              .order_by(PlayerTeamHistory.joined_at).all())


@router.get("/players/{player_id}/appearances", response_model=list[PlayerAppearanceOut])
def player_appearances(player_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Analyses where a human linked tracks to this player (newest match first)."""
    player = load_player(db, player_id, user, AccessLevel.READ)
    rows = (db.query(VideoAnalysis.id, Match.id, Match.opponent, Match.match_date, VideoAnalysis.analysis_mode,
                     func.array_agg(func.distinct(Detection.track_id)), func.count(Detection.id),
                     func.avg(Detection.confidence))
              .join(Detection, Detection.video_analysis_id == VideoAnalysis.id)
              .join(Video, Video.id == VideoAnalysis.video_id)
              .join(Match, Match.id == Video.match_id)
              .filter(Detection.player_id == player.id, Match.team_id == player.team_id)
              .group_by(VideoAnalysis.id, Match.id, Match.opponent, Match.match_date, VideoAnalysis.analysis_mode)
              .order_by(Match.match_date.desc())
              .all())
    return [
        PlayerAppearanceOut(analysis_id=analysis_id, match_id=match_id, opponent=opponent, match_date=match_date,
                            analysis_mode=mode, tracks=sorted(t for t in tracks if t is not None),
                            detections=count, mean_confidence=round(float(confidence or 0), 4))
        for analysis_id, match_id, opponent, match_date, mode, tracks, count, confidence in rows
    ]
