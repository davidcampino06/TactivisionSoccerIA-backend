"""Communication with the AI Service (Backend -> HTTP -> AI Service).

Patterns:
- Abstract Factory: ``AnalysisSourceFactory`` creates a FAMILY of objects that must match:
  the client that obtains the data and the validator that checks it. A real-video client must
  never be paired with a validator that accepts simulated data, and vice versa.
    * RealVideoSourceFactory  -> HttpVideoAnalysisClient  + AIResponseValidator(REAL_VIDEO_ANALYSIS)
    * SimulationSourceFactory -> HttpSimulationClient     + AIResponseValidator(SIMULATION_MODE)
- Factory Method: ``AnalysisSourceFactory.create_client`` is the factory method each concrete
  factory overrides; ``source_factory_for(mode)`` picks the factory.
- Decorator: ``RetryingAIClient`` and ``LoggingAIClient`` add retries and timing to ANY client
  without modifying it (Open/Closed).
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from config import settings

logger = logging.getLogger("tactivision.ai_client")

MODE_REAL = "REAL_VIDEO_ANALYSIS"
MODE_SIMULATION = "SIMULATION_MODE"


class AIServiceError(Exception):
    """The AI Service could not be reached or answered with an error.

    ``str(error)`` is the technical detail (English, for the logs); ``user_message`` is what the
    coach sees in the app (Spanish), without internal details.
    """

    default_user_message = "No se pudo completar el análisis con el servicio de IA. Intenta de nuevo."

    def __init__(self, message: str, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or self.default_user_message


class AIResponseError(AIServiceError):
    """The AI Service answered, but the payload is not valid."""

    default_user_message = "La respuesta del servicio de IA no es válida; el análisis se descartó."


def _user_message_for_status(status_code: int) -> str:
    if status_code == 503:
        return "El modelo de IA no está disponible en este momento. Intenta más tarde."
    if status_code in (400, 413, 415, 422):
        return "El servicio de IA no pudo procesar este video (formato, tamaño o contenido no válido)."
    return AIServiceError.default_user_message


# ------------------------------------------------------------------ validation
class _IndicatorPayload(BaseModel):
    name: str = Field(max_length=255)
    value: float
    unit: str = Field(max_length=50)
    threshold: float | None = None
    samples: int | None = Field(default=None, ge=0)
    exceed_ratio: float | None = Field(default=None, ge=0, le=1)


class _RecommendationPayload(BaseModel):
    issue_id: str
    title: str
    team: Literal["TEAM_A", "TEAM_B", "MATCH"] | None = None
    recommendation: str
    evidence: str
    confidence: float = Field(ge=0, le=1)
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    related_indicators: list[str]
    # seen / meaning / coach texts and an example frame (AI Service issue_examples.py); optional so
    # an older AI Service still works.
    explanation: dict[str, Any] | None = None


class _StrengthPayload(BaseModel):
    """Something the team did well (AI Service tactical_strengths.py)."""
    id: str
    code: str = Field(max_length=50)
    title: str
    team: Literal["TEAM_A", "TEAM_B", "MATCH"]
    evidence: str
    confidence: float = Field(ge=0, le=1)
    related_indicators: list[str] = []
    # seen / meaning / keep texts and an example frame.
    explanation: dict[str, Any] | None = None


class _DetectionPayload(BaseModel):
    frame_number: int = Field(ge=0)
    timestamp: float = Field(ge=0)
    object_type: Literal["PLAYER", "BALL"]
    confidence: float = Field(ge=0, le=1)
    bounding_box_x: float
    bounding_box_y: float
    bounding_box_width: float = Field(ge=0)
    bounding_box_height: float = Field(ge=0)
    track_id: int | None = None


class SnapshotPayload(BaseModel):
    """Best crop of one track (the AI's track_crops.py): a small JPEG in base64.

    The response keeps these as plain dicts and the adapter validates each one on its own, so a bad
    photo is skipped without failing the whole analysis."""
    track_id: int
    frame_number: int = Field(ge=0)
    timestamp: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    width: int = Field(gt=0, le=1000)
    height: int = Field(gt=0, le=1000)
    image_jpeg_base64: str = Field(max_length=90_000)


class TrackLinkPayload(BaseModel):
    """Track ``to_track`` looks like ``from_track`` cut in two (the AI's track_stitching.py).

    Kept as plain dicts in the response and validated one by one by the adapter, like the photos:
    a bad suggestion is skipped, the analysis is saved anyway."""
    from_track: int = Field(ge=0)
    to_track: int = Field(ge=0)
    from_last_frame: int = Field(ge=0)
    to_first_frame: int = Field(ge=0)
    gap_seconds: float = Field(gt=0, le=60)
    distance_heights: float = Field(ge=0, le=100)
    color_distance: float | None = Field(default=None, ge=0, le=500)
    same_team: bool | None = None
    confidence: float = Field(ge=0, le=1)


class RoleSuggestionPayload(BaseModel):
    """A track whose shirt is of no team (the AI's role_suggestions.py)."""
    track_id: int = Field(ge=0)
    suggestion: Literal["REFEREE", "GOALKEEPER_OR_REFEREE"]
    kit_group: int = Field(ge=1, le=100)
    kit_color: str = Field(pattern=r"^#[0-9a-f]{6}$")
    kit_tracks: int = Field(ge=1, le=1000)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=300)


class _NetworkNodePayload(BaseModel):
    track_id: int
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    degree: int = Field(ge=0)
    group: int = Field(ge=0)


class _TeamNetworkPayload(BaseModel):
    nodes: list[_NetworkNodePayload] = Field(max_length=40)
    links: list[tuple[int, int]] = Field(max_length=800)
    groups: int = Field(ge=0)
    isolated: list[int]
    diameter: int = Field(ge=0)
    hops: dict[str, dict[str, int]]


class _ProximityNetworkPayload(BaseModel):
    """Graph of supports between team-mates computed by the AI (graph + BFS)."""
    frame_number: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    link_distance: float = Field(gt=0, le=1)
    teams: dict[Literal["TEAM_A", "TEAM_B"], _TeamNetworkPayload]


class AIAnalysisPayload(BaseModel):
    status: Literal["COMPLETED"]
    mode: Literal["REAL_VIDEO_ANALYSIS", "SIMULATION_MODE"]
    model: str
    model_version: str
    video: dict[str, Any]
    frames_processed: int = Field(ge=0)
    players_detected: int = Field(ge=0)
    ball_detected: bool
    detections: list[_DetectionPayload]
    tracking: list[dict[str, Any]]
    # Optional so an AI Service from before the photos still works.
    track_snapshots: list[dict[str, Any]] = Field(default=[], max_length=300)
    # Optional so an AI Service from before them still works: tracks cut in two, kits of no team.
    track_links: dict[str, Any] = {}
    track_role_suggestions: list[dict[str, Any]] = Field(default=[], max_length=300)
    tactical_indicators: list[_IndicatorPayload]
    proximity_network: _ProximityNetworkPayload | None = None
    possible_issues: list[dict[str, Any]]
    recommendations: list[_RecommendationPayload]
    # Optional so an AI Service from before strengths still works.
    strengths: list[_StrengthPayload] = []
    warnings: list[str] = []
    performance: dict[str, Any] = {}
    detection_stability: dict[str, Any] = {}
    teams: dict[str, Any] = {}


class AIResponseValidator:
    def __init__(self, expected_mode: str) -> None:
        self.expected_mode = expected_mode

    def validate(self, raw_payload: dict) -> AIAnalysisPayload:
        try:
            payload = AIAnalysisPayload.model_validate(raw_payload)
        except ValidationError as error:
            raise AIResponseError(f"Invalid AI response: {error.error_count()} validation errors.") from error
        if payload.mode != self.expected_mode:
            raise AIResponseError(f"Expected {self.expected_mode} but AI Service returned {payload.mode}.",
                                  "El servicio de IA devolvió un tipo de análisis distinto al solicitado.")
        indicator_names = {indicator.name for indicator in payload.tactical_indicators}
        for recommendation in payload.recommendations:
            if not set(recommendation.related_indicators) <= indicator_names:
                raise AIResponseError("A recommendation references an unknown indicator.")
        return payload


# --------------------------------------------------------------------- clients
class AIAnalysisClient(ABC):
    @abstractmethod
    def analyze(self, video_path: Path | None, options: dict) -> dict:
        ...


class _HttpTransport:
    """POST to the AI Service with the API key, turning failures into AIServiceError."""

    def __init__(self, base_url: str = settings.ai_service_url, api_key: str = settings.ai_service_api_key,
                 timeout_seconds: float = settings.ai_service_timeout_seconds) -> None:
        self._base_url = base_url
        self._headers = {"X-API-Key": api_key} if api_key else {}
        self._timeout = httpx.Timeout(timeout_seconds, connect=10.0)

    def _post(self, path: str, **kwargs) -> dict:
        try:
            response = httpx.post(f"{self._base_url}{path}", headers=self._headers, timeout=self._timeout, **kwargs)
        except httpx.TimeoutException as error:
            raise AIServiceError("AI Service timed out.",
                                 "El servicio de IA tardó demasiado. Intenta con un clip más corto (10 a 20 segundos).") from error
        except httpx.TransportError as error:
            raise AIServiceError(f"AI Service unreachable: {error}",
                                 "No se pudo contactar el servicio de IA. Intenta de nuevo en unos minutos.") from error
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise AIServiceError(f"AI Service error {response.status_code}: {str(detail)[:200]}",
                                 _user_message_for_status(response.status_code))
        return response.json()


class _HttpClientBase(_HttpTransport, AIAnalysisClient):
    """An analysis client that talks HTTP to the AI Service."""


class HttpVideoAnalysisClient(_HttpClientBase):
    """Uploads the real video file to POST /api/analyze."""

    FORM_FIELDS = ("confidence_threshold", "frame_stride", "max_frames", "team_a_attack_direction", "own_kit_color")

    def analyze(self, video_path: Path | None, options: dict) -> dict:
        if video_path is None or not video_path.exists():
            raise AIServiceError("Video file is missing on the backend storage.",
                                 "El archivo de video ya no está en el servidor; súbelo de nuevo.")
        form = {key: str(options[key]) for key in self.FORM_FIELDS if options.get(key) is not None}
        with video_path.open("rb") as video_file:
            return self._post("/api/analyze", data=form, files={"video": (video_path.name, video_file)})


# Frame cap of each analysis detail (the app offers these two): the clip check says how much of the
# video each one covers, because the AI takes frames from the start until the cap.
ANALYSIS_DETAILS = {"fast": {"frame_stride": 5, "max_frames": 120}, "full": {"frame_stride": 3, "max_frames": 300}}


class HttpClipCheckClient(_HttpTransport):
    """POST /api/video-quality: is the clip fit for the analysis, before spending one on it."""

    def check(self, video_path: Path) -> dict:
        if not video_path.exists():
            raise AIServiceError("Video file is missing on the backend storage.",
                                 "El archivo de video ya no está en el servidor; súbelo de nuevo.")
        form = {"fast_stride": ANALYSIS_DETAILS["fast"]["frame_stride"],
                "fast_max_frames": ANALYSIS_DETAILS["fast"]["max_frames"],
                "full_stride": ANALYSIS_DETAILS["full"]["frame_stride"],
                "full_max_frames": ANALYSIS_DETAILS["full"]["max_frames"]}
        with video_path.open("rb") as video_file:
            return self._post("/api/video-quality", data={k: str(v) for k, v in form.items()},
                              files={"video": (video_path.name, video_file)})


class HttpSimulationClient(_HttpClientBase):
    """SIMULATION MODE: no video is sent; the AI Service generates synthetic positions."""

    def analyze(self, video_path: Path | None, options: dict) -> dict:
        return self._post("/api/analyze/simulation", data={"frames": str(min(options.get("max_frames", 120), 2000))})


# ------------------------------------------------------------------ decorators
class AIClientDecorator(AIAnalysisClient):
    def __init__(self, wrapped: AIAnalysisClient) -> None:
        self._wrapped = wrapped

    def analyze(self, video_path: Path | None, options: dict) -> dict:
        return self._wrapped.analyze(video_path, options)


class RetryingAIClient(AIClientDecorator):
    """Retries only when the service is unreachable (e.g. Render free instance waking up)."""

    def __init__(self, wrapped: AIAnalysisClient, attempts: int = 3, backoff_seconds: float = 2.0) -> None:
        super().__init__(wrapped)
        self._attempts = attempts
        self._backoff = backoff_seconds

    def analyze(self, video_path, options):
        for attempt in range(1, self._attempts + 1):
            try:
                return super().analyze(video_path, options)
            except AIServiceError as error:
                retriable = "unreachable" in str(error) or "error 503" in str(error)
                if not retriable or attempt == self._attempts:
                    raise
                logger.warning("AI Service attempt %s failed (%s); retrying", attempt, error)
                time.sleep(self._backoff * attempt)
        raise AIServiceError("Unreachable")  # pragma: no cover


class LoggingAIClient(AIClientDecorator):
    def analyze(self, video_path, options):
        started = time.perf_counter()
        try:
            return super().analyze(video_path, options)
        finally:
            logger.info("AI analysis call took %.1f s", time.perf_counter() - started)


# ------------------------------------------------------- abstract factory family
class AnalysisSourceFactory(ABC):
    mode: str

    @abstractmethod
    def create_client(self) -> AIAnalysisClient:
        """Factory Method."""

    def create_validator(self) -> AIResponseValidator:
        return AIResponseValidator(self.mode)


class RealVideoSourceFactory(AnalysisSourceFactory):
    mode = MODE_REAL

    def create_client(self) -> AIAnalysisClient:
        return LoggingAIClient(RetryingAIClient(HttpVideoAnalysisClient()))


class SimulationSourceFactory(AnalysisSourceFactory):
    mode = MODE_SIMULATION

    def create_client(self) -> AIAnalysisClient:
        return LoggingAIClient(RetryingAIClient(HttpSimulationClient()))


_FACTORIES: dict[str, type[AnalysisSourceFactory]] = {
    MODE_REAL: RealVideoSourceFactory,
    MODE_SIMULATION: SimulationSourceFactory,
}


def source_factory_for(mode: str) -> AnalysisSourceFactory:
    try:
        return _FACTORIES[mode]()
    except KeyError as error:
        raise ValueError(f"Unknown analysis mode {mode}") from error


def register_source_factory(mode: str, factory: type[AnalysisSourceFactory]) -> None:
    """Allows tests (or future sources) to plug in another family."""
    _FACTORIES[mode] = factory


def check_ai_service_health() -> str:
    try:
        response = httpx.get(f"{settings.ai_service_url}/api/health", timeout=5.0)
        return "OK" if response.status_code == 200 else "ERROR"
    except httpx.HTTPError:
        return "UNREACHABLE"
