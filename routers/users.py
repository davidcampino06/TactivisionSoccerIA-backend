"""Administrator: manage users and view registered teams and system health.

The administrator never sees tactical content (analyses, plays, reports, indicators). Here he only
gets counts and registration data; aggregated counts read across teams with ``rls.bypass``.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import rls
from config import settings
from database import get_db, get_database_status
from errors import AppError
from dependencies import require_roles
from models import Match, Player, Team, User, UserRole, Video, VideoAnalysis, utc_now
from schemas import AdminUserOut, AdminUserUpdate, TeamAdminOut
from services.ai_client import check_ai_service_health
from services.analysis_queue import AnalysisJobQueue

router = APIRouter(prefix="/api/admin", tags=["Administration"])
admin_only = require_roles(UserRole.ADMINISTRATOR)


def _team_names(db: Session) -> tuple[dict[str, str], dict[str, str]]:
    """(team id -> name, coach id -> team name)."""
    teams = db.query(Team.id, Team.name, Team.coach_id).all()
    return {team_id: name for team_id, name, _ in teams}, {coach: name for _, name, coach in teams if coach}


def _admin_user(user: User, by_id: dict[str, str], by_coach: dict[str, str]) -> AdminUserOut:
    team_name = by_id.get(user.team_id or "") or by_coach.get(user.id)
    return AdminUserOut(**AdminUserOut.model_validate(user).model_dump(exclude={"team_name"}), team_name=team_name)


@router.get("/users", response_model=list[AdminUserOut])
def list_users(role: str | None = Query(default=None), q: str | None = Query(default=None, max_length=100),
               _: User = Depends(admin_only), db: Session = Depends(get_db)):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role.upper())
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.filter(or_(User.first_name.ilike(pattern), User.last_name.ilike(pattern), User.email.ilike(pattern)))
    by_id, by_coach = _team_names(db)
    return [_admin_user(user, by_id, by_coach) for user in query.order_by(User.created_at.desc()).all()]


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(user_id: str, body: AdminUserUpdate, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "User not found.")
    if user.role == UserRole.ADMINISTRATOR:
        raise AppError(status.HTTP_403_FORBIDDEN, "ADMIN_MANAGED_BY_CONFIG", "Administrator accounts are managed by configuration.")
    if body.role and body.role != user.role:
        owns_team = db.query(Team).filter(Team.coach_id == user.id).first()
        if owns_team or user.team_id:
            raise AppError(status.HTTP_409_CONFLICT, "ROLE_CHANGE_TEAM_LINKED", "Cannot change the role of a user linked to a team.")
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    db.commit()
    by_id, by_coach = _team_names(db)
    return _admin_user(user, by_id, by_coach)


@router.get("/teams", response_model=list[TeamAdminOut])
def list_registered_teams(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Registration data and counts per team: never the matches, analyses or plays themselves."""
    teams = db.query(Team).order_by(Team.created_at.desc()).all()
    coaches = {user.id: f"{user.first_name} {user.last_name}" for user in db.query(User).filter(User.role == UserRole.COACH)}
    analysts = dict(db.query(User.team_id, func.count()).filter(User.role == UserRole.ANALYST, User.team_id.isnot(None))
                      .group_by(User.team_id).all())
    with rls.bypass(db):  # counts only
        players = dict(db.query(Player.team_id, func.count()).filter(Player.status != "INACTIVE").group_by(Player.team_id).all())
        matches = dict(db.query(Match.team_id, func.count()).group_by(Match.team_id).all())
        analyses = dict(db.query(Match.team_id, func.count(VideoAnalysis.id))
                          .join(Video, Video.match_id == Match.id).join(VideoAnalysis, VideoAnalysis.video_id == Video.id)
                          .group_by(Match.team_id).all())
    return [TeamAdminOut(
        **TeamAdminOut.model_validate(team).model_dump(exclude={"coach_name", "analysts", "players", "matches", "analyses"}),
        coach_name=coaches.get(team.coach_id or ""), analysts=analysts.get(team.id, 0), players=players.get(team.id, 0),
        matches=matches.get(team.id, 0), analyses=analyses.get(team.id, 0),
    ) for team in teams]


@router.get("/overview")
def overview(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Platform totals, the live analysis queue and the system configuration."""
    roles = dict(db.query(User.role, func.count()).group_by(User.role).all())
    inactive = db.query(func.count(User.id)).filter(User.is_active.is_(False)).scalar() or 0
    since = utc_now() - timedelta(days=13)
    signups = dict(db.query(func.date(User.created_at), func.count()).filter(User.created_at >= since)
                     .group_by(func.date(User.created_at)).all())
    days = [(since + timedelta(days=offset)).date() for offset in range(14)]
    teams = db.query(func.count(Team.id)).scalar() or 0

    queue = AnalysisJobQueue()
    with rls.bypass(db):  # totals and queue metadata only (no indicators, no recommendations)
        matches = db.query(func.count(Match.id)).scalar() or 0
        videos = db.query(func.count(Video.id)).scalar() or 0
        by_status = dict(db.query(VideoAnalysis.status, func.count()).group_by(VideoAnalysis.status).all())
        by_mode = dict(db.query(VideoAnalysis.analysis_mode, func.count()).group_by(VideoAnalysis.analysis_mode).all())
        running = (db.query(VideoAnalysis.id, VideoAnalysis.status, VideoAnalysis.analysis_mode, VideoAnalysis.started_at,
                            Team.name)
                     .join(Video, Video.id == VideoAnalysis.video_id).join(Match, Match.id == Video.match_id)
                     .join(Team, Team.id == Match.team_id)
                     .filter(VideoAnalysis.status.in_(("PENDING", "PROCESSING"))).all())
    jobs = [{"team": team, "status": state, "mode": mode,
             "started_at": started.isoformat() if started else None, "position": queue.position(analysis_id)}
            for analysis_id, state, mode, started, team in running]
    jobs.sort(key=lambda job: (job["status"] != "PROCESSING", job["position"] or 0))

    return {
        "users": {"total": sum(roles.values()), "by_role": roles, "inactive": inactive,
                  "signups": [{"date": day.isoformat(), "count": signups.get(day, 0)} for day in days]},
        "teams": teams, "matches": matches, "videos": videos,
        "analyses": {"total": sum(by_status.values()), "by_status": by_status, "by_mode": by_mode},
        "queue": {"waiting": len(queue), "mode": "sync" if queue.synchronous else "queue", "jobs": jobs},
        "system": {
            "backend": "OK", "database": get_database_status(), "ai_service": check_ai_service_health(),
            "environment": settings.environment, "row_level_security": settings.database_rls,
            "encrypted_passwords": settings.require_encrypted_passwords, "api_docs": settings.enable_docs,
            "simulation_mode": settings.allow_simulation_mode,
        },
    }
