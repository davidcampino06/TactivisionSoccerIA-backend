"""SQLAlchemy models. They map 1:1 to TactiSoccerIA-db/sql/schema.sql (the ERD).

The database schema is owned by the DB repository; the backend does not
create tables automatically in production.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Naive UTC timestamp (the ERD uses TIMESTAMP without time zone)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


Decimal4 = Numeric(10, 4, asdecimal=False)


class UserRole:
    ADMINISTRATOR = "ADMINISTRATOR"
    COACH = "COACH"
    ANALYST = "ANALYST"
    SELF_REGISTRATION = (COACH, ANALYST)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(255))
    profile_image_url: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    coach_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(255))
    invitation_code: Mapped[str] = mapped_column(String(20), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str] = mapped_column(String(255))
    shirt_number: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[str | None] = mapped_column(String(255))
    preferred_foot: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(255), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class PlayerTeamHistory(Base):
    __tablename__ = "player_team_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    left_at: Mapped[datetime | None] = mapped_column(DateTime)
    withdrawal_reason: Mapped[str | None] = mapped_column(String(255))


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    opponent: Mapped[str] = mapped_column(String(255))
    is_home: Mapped[bool] = mapped_column(Boolean, default=True)
    match_date: Mapped[datetime] = mapped_column(DateTime)
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(255), default="SCHEDULED")


class MatchEvent(Base):
    __tablename__ = "match_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    minute: Mapped[int] = mapped_column(Integer)
    second: Mapped[int] = mapped_column(Integer, default=0)
    event_type: Mapped[str] = mapped_column(String(255))
    zone: Mapped[str | None] = mapped_column(String(255))
    source_x: Mapped[float | None] = mapped_column(Decimal4)
    source_y: Mapped[float | None] = mapped_column(Decimal4)
    result: Mapped[str | None] = mapped_column(String(255))


class Formation(Base):
    __tablename__ = "formations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(String(255))
    player_count: Mapped[int] = mapped_column(Integer, default=11)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class MatchFormation(Base):
    __tablename__ = "match_formations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    formation_id: Mapped[str] = mapped_column(ForeignKey("formations.id", ondelete="CASCADE"))


class TacticalPlay(Base):
    __tablename__ = "tactical_plays"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(255))
    action_type: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    is_reusable: Mapped[bool] = mapped_column(Boolean, default=True)


class TacticalPlayVersion(Base):
    __tablename__ = "tactical_play_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tactical_play_id: Mapped[str] = mapped_column(ForeignKey("tactical_plays.id", ondelete="CASCADE"))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    version_number: Mapped[int] = mapped_column(Integer)
    configuration_data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)


class MatchTacticalPlay(Base):
    __tablename__ = "match_tactical_plays"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    tactical_play_id: Mapped[str] = mapped_column(ForeignKey("tactical_plays.id", ondelete="CASCADE"))


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(50))
    file_size: Mapped[int] = mapped_column(BigInteger)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    status: Mapped[str] = mapped_column(String(50), default="UPLOADED")


class VideoAnalysis(Base):
    __tablename__ = "video_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    analysis_mode: Mapped[str] = mapped_column(String(30), default="REAL_VIDEO_ANALYSIS")
    confidence_threshold: Mapped[float | None] = mapped_column(Decimal4)
    model_name: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(50))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    warning_message: Mapped[str | None] = mapped_column(String(255))

    video: Mapped[Video] = relationship(lazy="joined")


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_analysis_id: Mapped[str] = mapped_column(ForeignKey("video_analyses.id", ondelete="CASCADE"))
    player_id: Mapped[str | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"))
    frame_number: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[float] = mapped_column(Decimal4)
    object_type: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Decimal4)
    bounding_box_x: Mapped[float] = mapped_column(Decimal4)
    bounding_box_y: Mapped[float] = mapped_column(Decimal4)
    bounding_box_width: Mapped[float] = mapped_column(Decimal4)
    bounding_box_height: Mapped[float] = mapped_column(Decimal4)
    player_number: Mapped[int | None] = mapped_column(Integer)
    track_id: Mapped[int | None] = mapped_column(Integer)


class TacticalIndicator(Base):
    __tablename__ = "tactical_indicators"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_analysis_id: Mapped[str] = mapped_column(ForeignKey("video_analyses.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    value: Mapped[float] = mapped_column(Decimal4)
    unit: Mapped[str] = mapped_column(String(50))
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    threshold: Mapped[float | None] = mapped_column(Decimal4)


class RecommendationStatus:
    GENERATED = "GENERATED"
    REVIEWED = "REVIEWED"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Decimal4)
    evidence: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    status: Mapped[str] = mapped_column(String(50), default=RecommendationStatus.GENERATED)


class RecommendationIndicator(Base):
    __tablename__ = "recommendation_indicators"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("ai_recommendations.id", ondelete="CASCADE"))
    indicator_id: Mapped[str] = mapped_column(ForeignKey("tactical_indicators.id", ondelete="CASCADE"))


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    generated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(255))
    report_type: Mapped[str] = mapped_column(String(50))
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    version: Mapped[int] = mapped_column(Integer, default=1)
    snapshot_data: Mapped[str] = mapped_column(Text)
