"""Request/response contracts of the Backend API (Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------- auth / users
# Password fields carry "rsa:<base64>" (encrypted in the browser), so the schema only bounds the
# raw size; the real rules (password_policy.py) are checked after decryption.
EncryptedPassword = Annotated[str, Field(min_length=1, max_length=1024)]


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: EncryptedPassword
    phone: str | None = Field(default=None, max_length=255)
    role: Literal["COACH", "ANALYST"]  # ADMINISTRATOR can never self-register


class LoginRequest(BaseModel):
    email: EmailStr
    password: EncryptedPassword


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class PasswordRecoveryRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    token: str
    new_password: EncryptedPassword


class ChangePasswordRequest(BaseModel):
    current_password: EncryptedPassword
    new_password: EncryptedPassword


class UserOut(ORMModel):
    id: str
    first_name: str
    last_name: str
    email: str
    phone: str | None
    profile_image_url: str | None
    role: str
    team_id: str | None
    is_active: bool
    created_at: datetime


class ProfileUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=255)
    last_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=255)
    profile_image_url: str | None = Field(default=None, max_length=255)


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    role: Literal["COACH", "ANALYST"] | None = None


# ------------------------------------------------------------------------ teams
class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    category: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=255)


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    category: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class TeamSummaryOut(ORMModel):
    """What an ADMINISTRATOR may see: registration data only, no tactical content."""

    id: str
    name: str
    category: str | None
    city: str | None
    is_active: bool
    created_at: datetime


class TeamOut(TeamSummaryOut):
    coach_id: str
    description: str | None
    invitation_code: str | None = None  # only filled for the coach


class JoinTeamRequest(BaseModel):
    invitation_code: str = Field(min_length=4, max_length=20)


# ---------------------------------------------------------------------- players
PreferredFoot = Literal["RIGHT", "LEFT", "BOTH"]


class PlayerCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    shirt_number: int | None = Field(default=None, ge=0, le=99)
    position: str | None = Field(default=None, max_length=255)
    preferred_foot: PreferredFoot | None = None


class PlayerUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=255)
    last_name: str | None = Field(default=None, min_length=1, max_length=255)
    shirt_number: int | None = Field(default=None, ge=0, le=99)
    position: str | None = Field(default=None, max_length=255)
    preferred_foot: PreferredFoot | None = None
    status: Literal["ACTIVE", "INJURED", "SUSPENDED", "INACTIVE"] | None = None


class PlayerRemoveRequest(BaseModel):
    withdrawal_reason: str = Field(min_length=2, max_length=255)


class PlayerOut(ORMModel):
    id: str
    team_id: str | None
    first_name: str
    last_name: str
    shirt_number: int | None
    position: str | None
    preferred_foot: str | None
    status: str
    created_at: datetime


class PlayerHistoryOut(ORMModel):
    id: str
    player_id: str
    team_id: str
    joined_at: datetime
    left_at: datetime | None
    withdrawal_reason: str | None


class PlayerAppearanceOut(BaseModel):
    """An analysis where a human linked one or more tracks to the player."""
    analysis_id: str
    match_id: str
    opponent: str
    match_date: datetime
    analysis_mode: str
    tracks: list[int]
    detections: int
    mean_confidence: float


# ---------------------------------------------------------------------- matches
class MatchCreate(BaseModel):
    opponent: str = Field(min_length=1, max_length=255)
    is_home: bool = True
    match_date: datetime
    location: str | None = Field(default=None, max_length=255)
    status: Literal["SCHEDULED", "PLAYED", "CANCELLED"] = "SCHEDULED"


class MatchUpdate(BaseModel):
    opponent: str | None = Field(default=None, min_length=1, max_length=255)
    is_home: bool | None = None
    match_date: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    status: Literal["SCHEDULED", "PLAYED", "CANCELLED"] | None = None


class MatchResultUpdate(BaseModel):
    home_score: int = Field(ge=0, le=99)
    away_score: int = Field(ge=0, le=99)


class MatchOut(ORMModel):
    id: str
    team_id: str
    opponent: str
    is_home: bool
    match_date: datetime
    home_score: int | None
    away_score: int | None
    result: str | None
    location: str | None
    status: str


class MatchNeighborsOut(BaseModel):
    previous: MatchOut | None
    current: MatchOut
    next: MatchOut | None


class MatchEventCreate(BaseModel):
    minute: int = Field(ge=0, le=130)
    second: int = Field(default=0, ge=0, le=59)
    event_type: str = Field(min_length=1, max_length=255)
    zone: str | None = Field(default=None, max_length=255)
    source_x: float | None = Field(default=None, ge=0, le=105)
    source_y: float | None = Field(default=None, ge=0, le=68)
    result: str | None = Field(default=None, max_length=255)


class MatchEventOut(ORMModel):
    id: str
    match_id: str
    minute: int
    second: int
    event_type: str
    zone: str | None
    source_x: float | None
    source_y: float | None
    result: str | None


# ------------------------------------------------------------ formations / plays
class FormationCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255, examples=["4-3-3"])
    description: str | None = Field(default=None, max_length=255)
    player_count: int = Field(default=11, ge=1, le=11)

    @field_validator("name")
    @classmethod
    def validate_formation_name(cls, value: str) -> str:
        parts = value.split("-")
        if all(part.isdigit() for part in parts) and sum(int(part) for part in parts) != 10:
            raise ValueError("Numeric formations must describe 10 outfield players (e.g. 4-3-3).")
        return value


class FormationOut(ORMModel):
    id: str
    name: str
    description: str | None
    player_count: int
    created_at: datetime


class MatchFormationRequest(BaseModel):
    formation_id: str


MAX_CONFIGURATION_BYTES = 64_000


def _check_configuration_size(value: dict[str, Any]) -> dict[str, Any]:
    """A board has at most a few dozen tokens and arrows: reject oversized payloads."""
    import json
    if len(json.dumps(value, ensure_ascii=False).encode()) > MAX_CONFIGURATION_BYTES:
        raise ValueError(f"Configuration is larger than {MAX_CONFIGURATION_BYTES} bytes.")
    return value


class TacticalPlayCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    action_type: str | None = Field(default=None, max_length=255)
    is_reusable: bool = True
    configuration: dict[str, Any] = Field(
        default_factory=dict, description="Initial version: positions, arrows, notes (JSON)."
    )

    _size = field_validator("configuration")(_check_configuration_size)


class TacticalPlayUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    action_type: str | None = Field(default=None, max_length=255)
    is_reusable: bool | None = None


class TacticalPlayOut(ORMModel):
    id: str
    team_id: str
    name: str
    description: str | None
    action_type: str | None
    created_at: datetime
    is_reusable: bool


class TacticalPlaySummaryOut(TacticalPlayOut):
    """List item: the play plus its current version, so the list can draw a preview."""
    version_count: int
    current_version_number: int | None
    updated_at: datetime | None
    configuration: dict[str, Any]


class TacticalPlayVersionCreate(BaseModel):
    """New version. With ``base_version_id`` the version is cloned (Prototype) and
    ``configuration`` is applied as a patch over the clone."""

    base_version_id: str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)

    _size = field_validator("configuration")(_check_configuration_size)


class TacticalPlayVersionOut(ORMModel):
    id: str
    tactical_play_id: str
    created_by: str | None
    version_number: int
    configuration: dict[str, Any]
    created_at: datetime
    is_current: bool


class MatchTacticalPlayRequest(BaseModel):
    tactical_play_id: str


# ----------------------------------------------------------------- videos / AI
class VideoOut(ORMModel):
    id: str
    match_id: str
    file_name: str
    format: str
    file_size: int
    duration_seconds: int | None
    uploaded_at: datetime
    status: str


class AnalysisRequest(BaseModel):
    mode: Literal["REAL_VIDEO_ANALYSIS", "SIMULATION_MODE"] = "REAL_VIDEO_ANALYSIS"
    confidence_threshold: float = Field(default=0.25, ge=0.05, le=0.95)
    frame_stride: int = Field(default=3, ge=1, le=60)
    max_frames: int = Field(default=300, ge=1, le=5000)
    team_a_attack_direction: Literal["unknown", "left_to_right", "right_to_left"] = "unknown"


class VideoAnalysisOut(ORMModel):
    id: str
    video_id: str
    status: str
    analysis_mode: str
    confidence_threshold: float | None
    model_name: str | None
    model_version: str | None
    started_at: datetime | None
    completed_at: datetime | None
    warning_message: str | None
    queue_position: int | None = None


class DetectionOut(ORMModel):
    id: str
    player_id: str | None
    frame_number: int
    timestamp: float
    object_type: str
    confidence: float
    bounding_box_x: float
    bounding_box_y: float
    bounding_box_width: float
    bounding_box_height: float
    player_number: int | None
    track_id: int | None


class TrackAssignmentRequest(BaseModel):
    player_id: str | None = Field(description="null removes the identification")


class TacticalIndicatorOut(ORMModel):
    id: str
    video_analysis_id: str
    name: str
    value: float
    unit: str
    calculated_at: datetime
    threshold: float | None


class RecommendationOut(ORMModel):
    id: str
    match_id: str
    title: str
    description: str
    severity: str
    confidence: float
    evidence: str
    created_at: datetime
    status: str
    indicator_names: list[str] = []


class RecommendationStatusUpdate(BaseModel):
    action: Literal["review", "confirm", "dismiss"]


class AnalysisResultOut(BaseModel):
    analysis: VideoAnalysisOut
    label: str
    summary: dict[str, Any]
    indicators: list[TacticalIndicatorOut]
    recommendations: list[RecommendationOut]


# --------------------------------------------------------------------- reports
class ReportCreate(BaseModel):
    report_type: Literal["MATCH", "VIDEO_ANALYSIS", "TEAM_EVOLUTION"]
    title: str | None = Field(default=None, max_length=255)
    match_id: str | None = None
    analysis_id: str | None = None
    match_ids: list[str] | None = None


class ReportOut(ORMModel):
    id: str
    team_id: str
    generated_by: str | None
    title: str
    report_type: str
    generated_at: datetime
    version: int


class ReportDetailOut(ReportOut):
    snapshot: dict[str, Any]


class NotificationOut(BaseModel):
    event: str
    team_id: str
    analysis_id: str
    message: str
    created_at: datetime


TokenResponse.model_rebuild()
