"""TactiVision IA Backend (FastAPI).

Frontend -> Backend -> PostgreSQL
Frontend -> Backend -> AI Service      (the Frontend never calls the AI Service)
"""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import database
from config import describe_database_url, settings
from database import get_database_status
from routers import (
    analyses, auth, formations, insights, matches, players, recommendations, reports, tactical_plays, teams,
    users, videos,
)
from services.ai_client import check_ai_service_health
from services.analysis_facade import get_analysis_facade
from services.analysis_queue import AnalysisJob

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("tactivision.backend")


def recover_interrupted_analyses() -> None:
    """After a restart: PROCESSING jobs were lost -> FAILED; PENDING jobs are queued again."""
    if database.SessionLocal is None:
        return
    from models import VideoAnalysis
    from services.analysis_state import AnalysisStateMachine

    try:
        with database.SessionLocal() as db:
            interrupted = db.query(VideoAnalysis).filter(VideoAnalysis.status == "PROCESSING").all()
            for analysis in interrupted:
                AnalysisStateMachine(analysis).fail("Interrupted by a server restart. Start the analysis again.")
                analysis.video.status = "UPLOADED"
            pending_ids = [a.id for a in db.query(VideoAnalysis).filter(VideoAnalysis.status == "PENDING")]
            db.commit()
        facade = get_analysis_facade()
        for analysis_id in pending_ids:
            facade._queue.submit(AnalysisJob(analysis_id, {}))
        if interrupted or pending_ids:
            logger.info("Recovered analyses: %s failed, %s re-queued", len(interrupted), len(pending_ids))
    except Exception:
        logger.exception("Could not recover analyses (is the schema applied?)")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Database target: %s", describe_database_url(settings.database_url))
    get_analysis_facade()  # connects the analysis queue to its handler
    # In background: the server must open its port even if the database is slow or unreachable.
    threading.Thread(target=recover_interrupted_analyses, name="analysis-recovery", daemon=True).start()
    yield


app = FastAPI(title="TactiVision IA Backend", version="0.6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, users, teams, players, matches, formations, tactical_plays, videos, analyses,
               recommendations, reports, insights):
    app.include_router(module.router)


@app.get("/api/hello")
def get_hello():
    return {"message": "Hello from TactiVision IA backend"}


@app.get("/api/status")
def get_status():
    """Original prototype contract (backend + database) plus the AI Service state."""
    return {
        "backend": "OK",
        "database": get_database_status(),
        "ai_service": check_ai_service_health(),
    }
