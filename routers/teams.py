"""Teams, invitation codes and analysts."""

import re
import secrets

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

import rls
from database import get_db
from errors import AppError
from dependencies import AccessLevel, get_current_user, load_team, require_roles
from models import Team, TeamCrest, User, UserRole, utc_now
from schemas import JoinTeamRequest, TeamCreate, TeamOut, TeamUpdate, UserOut
from services.analysis_events import ANALYST_JOINED, AnalysisEvent, NotificationCenter
from services.team_crest import MAX_UPLOAD_BYTES, CrestError, normalize_crest

router = APIRouter(prefix="/api/teams", tags=["Teams"])
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to avoid confusion


def generate_invitation_code(db: Session, team_name: str) -> str:
    prefix = (re.sub(r"[^A-Z]", "", team_name.upper())[:5] or "TEAM")
    for _ in range(20):
        code = f"{prefix}-{''.join(secrets.choice(CODE_ALPHABET) for _ in range(4))}"
        with rls.bypass(db):  # codes are unique across ALL teams
            taken = db.query(Team.id).filter(Team.invitation_code == code).first()
        if not taken:
            return code
    raise AppError(status.HTTP_500_INTERNAL_SERVER_ERROR, "INVITATION_CODE_FAILED", "Could not generate an invitation code.")


def team_out(team: Team, user: User, db: Session) -> TeamOut:
    data = TeamOut.model_validate(team)
    if team.coach_id != user.id:
        data.invitation_code = None
    # Only the date: the image bytes are never read with the team.
    data.crest_updated_at = db.query(TeamCrest.updated_at).filter(TeamCrest.team_id == team.id).scalar()
    return data


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(body: TeamCreate, coach: User = Depends(require_roles(UserRole.COACH)), db: Session = Depends(get_db)):
    if db.query(Team).filter(Team.coach_id == coach.id).first():
        raise AppError(status.HTTP_409_CONFLICT, "COACH_HAS_TEAM", "A coach can manage only one team.")
    team = Team(coach_id=coach.id, invitation_code=generate_invitation_code(db, body.name), **body.model_dump())
    db.add(team)
    db.flush()
    db.get(User, coach.id).team_id = team.id
    db.commit()
    return team_out(team, coach, db)


@router.get("/mine", response_model=TeamOut)
def my_team(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    team = None
    if user.role == UserRole.COACH:
        team = db.query(Team).filter(Team.coach_id == user.id).first()
    elif user.role == UserRole.ANALYST and user.team_id:
        team = db.get(Team, user.team_id)
    if team is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "NO_TEAM", "You are not linked to a team yet.")
    return team_out(team, user, db)


@router.post("/join", response_model=TeamOut)
def join_team(body: JoinTeamRequest, analyst: User = Depends(require_roles(UserRole.ANALYST)),
              db: Session = Depends(get_db)):
    if analyst.team_id:
        raise AppError(status.HTTP_409_CONFLICT, "ALREADY_IN_TEAM", "You are already assigned to a team.")
    with rls.bypass(db):  # the analyst does not belong to the team yet
        team = db.query(Team).filter(Team.invitation_code == body.invitation_code.strip().upper()).first()
    if team is None or not team.is_active:
        raise AppError(status.HTTP_404_NOT_FOUND, "INVALID_INVITATION_CODE", "Invalid invitation code.")
    db.get(User, analyst.id).team_id = team.id
    db.commit()
    NotificationCenter().publish(AnalysisEvent(
        ANALYST_JOINED, team.id, None, f"{analyst.first_name} {analyst.last_name} se unió al equipo como analista.",
        actor_id=analyst.id,
    ))
    return team_out(team, analyst, db)


@router.get("/{team_id}", response_model=TeamOut)
def get_team(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return team_out(load_team(db, team_id, user, AccessLevel.READ), user, db)


@router.put("/{team_id}", response_model=TeamOut)
def update_team(team_id: str, body: TeamUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    team = load_team(db, team_id, user, AccessLevel.MANAGE)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(team, field, value)
    db.commit()
    return team_out(team, user, db)


@router.post("/{team_id}/invitation-code", response_model=TeamOut)
def regenerate_invitation_code(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    team = load_team(db, team_id, user, AccessLevel.MANAGE)
    team.invitation_code = generate_invitation_code(db, team.name)
    db.commit()
    return team_out(team, user, db)


@router.get("/{team_id}/analysts", response_model=list[UserOut])
def list_analysts(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.MANAGE)
    return db.query(User).filter(User.team_id == team_id, User.role == UserRole.ANALYST).all()


@router.delete("/{team_id}/analysts/{analyst_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_analyst(team_id: str, analyst_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.MANAGE)
    analyst = db.get(User, analyst_id)
    if analyst is None or analyst.team_id != team_id or analyst.role != UserRole.ANALYST:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Analyst not found in this team.")
    analyst.team_id = None
    db.commit()


# ------------------------------------------------------------------------- crest
@router.get("/{team_id}/crest")
def get_crest(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The crest PNG. People of the team only (also enforced by Row-Level Security)."""
    load_team(db, team_id, user, AccessLevel.READ)
    crest = db.get(TeamCrest, team_id)
    if crest is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "NO_CREST", "This team has no crest.")
    return Response(content=crest.image, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@router.put("/{team_id}/crest", response_model=TeamOut)
async def upload_crest(team_id: str, crest: UploadFile = File(...), user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Only the coach. The image is re-encoded as a 256 px PNG (services/team_crest.py)."""
    team = load_team(db, team_id, user, AccessLevel.MANAGE)
    raw = await crest.read(MAX_UPLOAD_BYTES + 1)
    try:
        image = normalize_crest(raw)
    except CrestError as error:
        raise AppError(status.HTTP_400_BAD_REQUEST, error.code, str(error)) from error
    stored = db.get(TeamCrest, team_id)
    if stored is None:
        db.add(TeamCrest(team_id=team_id, content_type="image/png", image=image, updated_at=utc_now()))
    else:
        stored.image, stored.updated_at = image, utc_now()
    db.commit()
    return team_out(team, user, db)


@router.delete("/{team_id}/crest", response_model=TeamOut)
def delete_crest(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    team = load_team(db, team_id, user, AccessLevel.MANAGE)
    stored = db.get(TeamCrest, team_id)
    if stored is not None:
        db.delete(stored)
        db.commit()
    return team_out(team, user, db)
