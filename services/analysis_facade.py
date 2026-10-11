"""Facade: one entry point for the complete video analysis use case.

Routers call ``VideoAnalysisFacade``; it coordinates validation, the State machine,
the FIFO queue, the AI source family (Abstract Factory), response validation, the
Adapter, persistence and the Observer notifications.

Flow (Sequence Diagram):
  request_analysis -> PENDING + queued -> run_analysis -> PROCESSING -> AI Service
  -> validate -> adapt -> persist -> COMPLETED (or FAILED) -> notify observers
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import insert
from sqlalchemy.orm import Session

import database
import rls
from config import settings
from models import Detection, Match, Video, VideoAnalysis
from services.ai_client import MODE_SIMULATION, AIServiceError, source_factory_for
from services.ai_result_adapter import AIResultAdapter
from services.analysis_events import (
    ANALYSIS_CANCELLED, ANALYSIS_COMPLETED, ANALYSIS_FAILED, ANALYSIS_QUEUED, ANALYSIS_STARTED,
    TACTICAL_ALERT, AnalysisEvent, NotificationCenter,
)
from services.analysis_queue import AnalysisJob, AnalysisJobQueue
from services.analysis_state import AnalysisStateMachine, InvalidStateTransition

logger = logging.getLogger("tactivision.analysis")


class AnalysisRequestError(ValueError):
    """The analysis cannot be started; ``code`` is translated to Spanish by the frontend."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


MODE_LABELS = {"REAL_VIDEO_ANALYSIS": "análisis de video real", "SIMULATION_MODE": "modo simulación"}


def video_file_path(video: Video) -> Path:
    return settings.upload_dir / video.file_path


class VideoAnalysisFacade:
    def __init__(self) -> None:
        self._queue = AnalysisJobQueue()
        self._notifications = NotificationCenter()
        self._queue.set_handler(self.run_analysis)

    # --------------------------------------------------------------- commands
    def request_analysis(self, db: Session, video: Video, options: dict) -> tuple[VideoAnalysis, int]:
        mode = options["mode"]
        if mode == MODE_SIMULATION and not settings.allow_simulation_mode:
            raise AnalysisRequestError("SIMULATION_DISABLED", "SIMULATION MODE is disabled on this server.")
        if mode != MODE_SIMULATION and not video_file_path(video).exists():
            raise AnalysisRequestError("VIDEO_FILE_MISSING", "The video file is not available on the server; upload it again.")
        busy = db.query(VideoAnalysis).filter(
            VideoAnalysis.video_id == video.id, VideoAnalysis.status.in_(("PENDING", "PROCESSING"))
        ).first()
        if busy:
            raise AnalysisRequestError("ANALYSIS_IN_PROGRESS", f"Video already has an analysis in progress ({busy.id}).")

        analysis = VideoAnalysis(
            video_id=video.id, status="PENDING", analysis_mode=mode,
            confidence_threshold=options["confidence_threshold"],
        )
        db.add(analysis)
        db.commit()
        team_id = self._team_id(db, video)
        self._notify(ANALYSIS_QUEUED, team_id, analysis.id, f"Análisis en cola ({MODE_LABELS.get(mode, mode)}).")
        position = self._queue.submit(AnalysisJob(analysis.id, options))
        db.refresh(analysis)
        return analysis, position

    def cancel_analysis(self, db: Session, analysis: VideoAnalysis) -> VideoAnalysis:
        machine = AnalysisStateMachine(analysis)
        machine.cancel()  # raises InvalidStateTransition when terminal
        self._queue.discard(analysis.id)
        db.commit()
        self._notify(ANALYSIS_CANCELLED, self._team_id(db, analysis.video), analysis.id, "Análisis cancelado.")
        return analysis

    def queue_position(self, analysis_id: str) -> int | None:
        return self._queue.position(analysis_id)

    # ------------------------------------------------------------ worker side
    def run_analysis(self, job: AnalysisJob) -> None:
        with rls.mark_system(database.SessionLocal()) as db:  # background job: not tied to a request
            analysis = db.get(VideoAnalysis, job.analysis_id)
            if analysis is None or analysis.status != "PENDING":
                return
            video = analysis.video
            match = db.get(Match, video.match_id)
            machine = AnalysisStateMachine(analysis)
            machine.start()
            video.status = "ANALYZING"
            db.commit()
            self._notify(ANALYSIS_STARTED, match.team_id, analysis.id, "Análisis iniciado.")

            try:
                factory = source_factory_for(analysis.analysis_mode)
                raw_result = factory.create_client().analyze(video_file_path(video), job.options)
                payload = factory.create_validator().validate(raw_result)
            except AIServiceError as error:
                logger.warning("Analysis %s failed in the AI Service: %s", analysis.id, error)
                self._fail(db, analysis, video, match.team_id, error.user_message)
                return
            except ValueError as error:
                logger.warning("Analysis %s failed: %s", analysis.id, error)
                self._fail(db, analysis, video, match.team_id, AIServiceError.default_user_message)
                return

            db.refresh(analysis)
            if analysis.status == "CANCELLED":
                logger.info("Analysis %s was cancelled while processing; results discarded", analysis.id)
                video.status = "UPLOADED"
                db.commit()
                return

            try:
                self._persist(db, analysis, video, match, payload)
            except Exception:  # database problems
                db.rollback()
                logger.exception("Persisting analysis %s failed", analysis.id)
                analysis = db.get(VideoAnalysis, job.analysis_id)
                self._fail(db, analysis, analysis.video, match.team_id, "No se pudieron guardar los resultados del análisis. Intenta de nuevo.")

    def _persist(self, db: Session, analysis: VideoAnalysis, video: Video, match: Match, payload) -> None:
        adapter = AIResultAdapter(payload, analysis.id, match.id)
        detection_rows = adapter.detection_rows()
        if detection_rows:
            db.execute(insert(Detection), detection_rows)
        db.add_all(adapter.indicators())
        recommendations, links = adapter.recommendations()
        db.add_all(recommendations)
        db.flush()
        db.add_all(links)

        analysis.model_name = payload.model[:100]
        analysis.model_version = payload.model_version[:50]
        video.duration_seconds = adapter.video_duration_seconds() or video.duration_seconds
        video.status = "ANALYZED"
        AnalysisStateMachine(analysis).complete(adapter.warning_message())
        db.commit()

        self._notify(
            ANALYSIS_COMPLETED, match.team_id, analysis.id,
            f"Análisis completado ({MODE_LABELS.get(payload.mode, payload.mode)}): "
            f"{len(payload.tactical_indicators)} indicadores y {len(recommendations)} posibles problemas.",
        )
        for recommendation in recommendations:
            if recommendation.severity == "HIGH":
                self._notify(TACTICAL_ALERT, match.team_id, analysis.id,
                             f"{recommendation.title} (confianza {round(recommendation.confidence * 100)} %)")

    def _fail(self, db: Session, analysis: VideoAnalysis, video: Video, team_id: str, reason: str) -> None:
        try:
            AnalysisStateMachine(analysis).fail(reason)
        except InvalidStateTransition:
            return
        video.status = "UPLOADED"
        db.commit()
        self._notify(ANALYSIS_FAILED, team_id, analysis.id, reason[:200])

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _team_id(db: Session, video: Video) -> str:
        return db.get(Match, video.match_id).team_id

    def _notify(self, event: str, team_id: str, analysis_id: str, message: str) -> None:
        self._notifications.publish(AnalysisEvent(event, team_id, analysis_id, message))


_facade: VideoAnalysisFacade | None = None


def get_analysis_facade() -> VideoAnalysisFacade:
    global _facade
    if _facade is None:
        _facade = VideoAnalysisFacade()
    return _facade
