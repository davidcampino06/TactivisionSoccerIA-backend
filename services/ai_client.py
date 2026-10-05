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
    """The AI Service could not be reached or answered with an error."""


class AIResponseError(AIServiceError):
    """The AI Service answered, but the payload is not valid."""


# ------------------------------------------------------------------ validation
class _IndicatorPayload(BaseModel):
    name: str = Field(max_length=255)
    value: float
    unit: str = Field(max_length=50)
    threshold: float | None = None


class _RecommendationPayload(BaseModel):
    issue_id: str
    title: str
    recommendation: str
    evidence: str
    confidence: float = Field(ge=0, le=1)
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    related_indicators: list[str]


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
    tactical_indicators: list[_IndicatorPayload]
    possible_issues: list[dict[str, Any]]
    recommendations: list[_RecommendationPayload]
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
            raise AIResponseError(f"Expected {self.expected_mode} but AI Service returned {payload.mode}.")
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


class _HttpClientBase(AIAnalysisClient):
    def __init__(self, base_url: str = settings.ai_service_url, api_key: str = settings.ai_service_api_key,
                 timeout_seconds: float = settings.ai_service_timeout_seconds) -> None:
        self._base_url = base_url
        self._headers = {"X-API-Key": api_key} if api_key else {}
        self._timeout = httpx.Timeout(timeout_seconds, connect=10.0)

    def _post(self, path: str, **kwargs) -> dict:
        try:
            response = httpx.post(f"{self._base_url}{path}", headers=self._headers, timeout=self._timeout, **kwargs)
        except httpx.TimeoutException as error:
            raise AIServiceError("AI Service timed out.") from error
        except httpx.TransportError as error:
            raise AIServiceError(f"AI Service unreachable: {error}") from error
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise AIServiceError(f"AI Service error {response.status_code}: {str(detail)[:200]}")
        return response.json()


class HttpVideoAnalysisClient(_HttpClientBase):
    """Uploads the real video file to POST /api/analyze."""

    FORM_FIELDS = ("confidence_threshold", "frame_stride", "max_frames", "team_a_attack_direction")

    def analyze(self, video_path: Path | None, options: dict) -> dict:
        if video_path is None or not video_path.exists():
            raise AIServiceError("Video file is missing on the backend storage.")
        form = {key: str(options[key]) for key in self.FORM_FIELDS if key in options}
        with video_path.open("rb") as video_file:
            return self._post("/api/analyze", data=form, files={"video": (video_path.name, video_file)})


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
