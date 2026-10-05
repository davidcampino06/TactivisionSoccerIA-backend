"""Authentication and authorization rules, enforced in the Backend (never only in the UI).

Team rules:
- A COACH manages only the team where teams.coach_id == user.id.
- An ANALYST accesses only the team in users.team_id (joined with an invitation code).
- An ADMINISTRATOR manages users and sees registered teams, but has NO access to private
  tactical content (players, matches, plays, videos, analyses, recommendations, reports).
"""

from __future__ import annotations

from enum import Enum

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
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
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error),
                            headers={"WWW-Authenticate": "Bearer"}) from error
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive.")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot perform this action.")
        return user

    return dependency


class TeamAccessPolicy:
    """Single place where team permissions are decided."""

    @staticmethod
    def can_access(user: User, team: Team, level: AccessLevel) -> bool:
        if user.role == UserRole.ADMINISTRATOR:
            return False
        if user.role == UserRole.COACH:
            return team.coach_id == user.id
        if user.role == UserRole.ANALYST:
            return level != AccessLevel.MANAGE and user.team_id == team.id
        return False

    @classmethod
    def ensure(cls, user: User, team: Team, level: AccessLevel) -> None:
        if not cls.can_access(user, team, level):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this team's content.")


def _get_or_404(db: Session, model, entity_id: str, label: str):
    entity = db.get(model, entity_id)
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found.")
    return entity


def load_team(db: Session, team_id: str, user: User, level: AccessLevel) -> Team:
    team = _get_or_404(db, Team, team_id, "Team")
    TeamAccessPolicy.ensure(user, team, level)
    return team


def load_player(db: Session, player_id: str, user: User, level: AccessLevel) -> Player:
    player = _get_or_404(db, Player, player_id, "Player")
    if player.team_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Player is not assigned to a team.")
    load_team(db, player.team_id, user, level)
    return player


def load_match(db: Session, match_id: str, user: User, level: AccessLevel) -> Match:
    match = _get_or_404(db, Match, match_id, "Match")
    load_team(db, match.team_id, user, level)
    return match


def load_video(db: Session, video_id: str, user: User, level: AccessLevel) -> Video:
    video = _get_or_404(db, Video, video_id, "Video")
    load_match(db, video.match_id, user, level)
    return video


def load_analysis(db: Session, analysis_id: str, user: User, level: AccessLevel) -> VideoAnalysis:
    analysis = _get_or_404(db, VideoAnalysis, analysis_id, "Video analysis")
    load_video(db, analysis.video_id, user, level)
    return analysis


def load_tactical_play(db: Session, play_id: str, user: User, level: AccessLevel) -> TacticalPlay:
    play = _get_or_404(db, TacticalPlay, play_id, "Tactical play")
    load_team(db, play.team_id, user, level)
    return play


def load_recommendation(db: Session, recommendation_id: str, user: User, level: AccessLevel) -> AIRecommendation:
    recommendation = _get_or_404(db, AIRecommendation, recommendation_id, "Recommendation")
    load_match(db, recommendation.match_id, user, level)
    return recommendation


def load_report(db: Session, report_id: str, user: User, level: AccessLevel) -> Report:
    report = _get_or_404(db, Report, report_id, "Report")
    load_team(db, report.team_id, user, level)
    return report
