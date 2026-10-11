"""Authentication and authorization rules, enforced in the Backend (never only in the UI).

Team rules:
- A COACH manages only the team where teams.coach_id == user.id.
- An ANALYST accesses only the team in users.team_id (joined with an invitation code).
- An ADMINISTRATOR manages users and sees registered teams, but has NO access to private
  tactical content (players, matches, plays, videos, analyses, recommendations, reports).

Isolation between teams: a user who does not belong to a team gets 404 for anything of that
team, exactly the same answer as for an id that does not exist. This way nobody can even
confirm that another team's match, player or video exists. 403 is kept only for members whose
role is not enough (an analyst trying to manage players) and for the administrator.
"""

from __future__ import annotations

from enum import Enum

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

import rls
from database import get_db
from errors import AppError
from models import (
    AIRecommendation,
    Match,
    Player,
    Report,
    TacticalPlay,
    Team,
    User,
    UserRole,
    Video,
    VideoAnalysis,
)
from security import InvalidTokenError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


class AccessLevel(Enum):
    READ = "read"              # coach owner or assigned analyst
    CONTRIBUTE = "contribute"  # same people: events, videos, analyses, reports, reviews
    MANAGE = "manage"          # coach owner only: team data, players, plays, deletions


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "NOT_AUTHENTICATED", "Not authenticated.",
                       headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as error:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "SESSION_EXPIRED", str(error),
                       headers={"WWW-Authenticate": "Bearer"}) from error
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "SESSION_EXPIRED", "User not found or inactive.")
    rls.identify_user(db, user)  # PostgreSQL now filters every query of this request by team
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise AppError(status.HTTP_403_FORBIDDEN, "ROLE_NOT_ALLOWED", "Your role cannot perform this action.")
        return user

    return dependency


class TeamAccessPolicy:
    """Single place where team permissions are decided."""

    @staticmethod
    def is_member(user: User, team: Team) -> bool:
        if user.role == UserRole.COACH:
            return team.coach_id == user.id
        if user.role == UserRole.ANALYST:
            return user.team_id == team.id
        return False

    @classmethod
    def can_access(cls, user: User, team: Team, level: AccessLevel) -> bool:
        if not cls.is_member(user, team):
            return False
        return user.role == UserRole.COACH or level != AccessLevel.MANAGE

    @staticmethod
    def reject_admin(user: User) -> None:
        if user.role == UserRole.ADMINISTRATOR:
            raise AppError(status.HTTP_403_FORBIDDEN, "ADMIN_NO_TACTICAL_ACCESS",
                           "Administrators cannot access teams' tactical content.")

    @classmethod
    def ensure(cls, user: User, team: Team, level: AccessLevel, label: str = "Team") -> None:
        cls.reject_admin(user)
        if not cls.is_member(user, team):
            raise not_found(label)
        if not cls.can_access(user, team, level):
            raise AppError(status.HTTP_403_FORBIDDEN, "ROLE_NOT_ALLOWED", "Your role cannot perform this action.")


def not_found(label: str) -> AppError:
    return AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"{label} not found.")


def _get_or_404(db: Session, model, entity_id: str, label: str):
    entity = db.get(model, entity_id)
    if entity is None:
        raise not_found(label)
    return entity


# Each loader checks permissions on the owning team; the 404 always names the resource that was
# requested, so an existing resource of another team looks exactly like a missing one.
def load_team(db: Session, team_id: str, user: User, level: AccessLevel, label: str = "Team") -> Team:
    TeamAccessPolicy.reject_admin(user)
    team = _get_or_404(db, Team, team_id, label)
    TeamAccessPolicy.ensure(user, team, level, label)
    return team


def load_player(db: Session, player_id: str, user: User, level: AccessLevel, label: str = "Player") -> Player:
    TeamAccessPolicy.reject_admin(user)
    player = _get_or_404(db, Player, player_id, label)
    if player.team_id is None:
        raise not_found(label)
    load_team(db, player.team_id, user, level, label)
    return player


def load_match(db: Session, match_id: str, user: User, level: AccessLevel, label: str = "Match") -> Match:
    TeamAccessPolicy.reject_admin(user)
    match = _get_or_404(db, Match, match_id, label)
    load_team(db, match.team_id, user, level, label)
    return match


def load_video(db: Session, video_id: str, user: User, level: AccessLevel, label: str = "Video") -> Video:
    TeamAccessPolicy.reject_admin(user)
    video = _get_or_404(db, Video, video_id, label)
    load_match(db, video.match_id, user, level, label)
    return video


def load_analysis(db: Session, analysis_id: str, user: User, level: AccessLevel,
                  label: str = "Video analysis") -> VideoAnalysis:
    TeamAccessPolicy.reject_admin(user)
    analysis = _get_or_404(db, VideoAnalysis, analysis_id, label)
    load_video(db, analysis.video_id, user, level, label)
    return analysis


def load_tactical_play(db: Session, play_id: str, user: User, level: AccessLevel,
                       label: str = "Tactical play") -> TacticalPlay:
    TeamAccessPolicy.reject_admin(user)
    play = _get_or_404(db, TacticalPlay, play_id, label)
    load_team(db, play.team_id, user, level, label)
    return play


def load_recommendation(db: Session, recommendation_id: str, user: User, level: AccessLevel,
                        label: str = "Recommendation") -> AIRecommendation:
    TeamAccessPolicy.reject_admin(user)
    recommendation = _get_or_404(db, AIRecommendation, recommendation_id, label)
    load_match(db, recommendation.match_id, user, level, label)
    return recommendation


def load_report(db: Session, report_id: str, user: User, level: AccessLevel, label: str = "Report") -> Report:
    TeamAccessPolicy.reject_admin(user)
    report = _get_or_404(db, Report, report_id, label)
    load_team(db, report.team_id, user, level, label)
    return report
