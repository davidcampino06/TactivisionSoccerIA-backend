"""Video upload and analysis requests (Frontend -> Backend; never Frontend -> AI Service)."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from errors import AppError
from dependencies import AccessLevel, get_current_user, load_match, load_video
from models import User, Video, VideoAnalysis
from schemas import AnalysisRequest, VideoAnalysisOut, VideoOut
from services.analysis_facade import AnalysisRequestError, get_analysis_facade, video_file_path

router = APIRouter(prefix="/api", tags=["Videos"])
ALLOWED_FORMATS = {".mp4": "MP4", ".mov": "MOV", ".avi": "AVI", ".mkv": "MKV", ".webm": "WEBM"}
CHUNK_BYTES = 1024 * 1024


def _store_upload(upload: UploadFile) -> tuple[str, str, str, int]:
    """Saves the uploaded file in UPLOAD_DIR in chunks. Returns (original name, stored name, format, size)."""
    original_name = Path(upload.filename or "video").name[:200]
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_FORMATS:
        raise AppError(status.HTTP_400_BAD_REQUEST, "INVALID_VIDEO_FORMAT", f"Invalid format. Allowed: {', '.join(ALLOWED_FORMATS)}")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4()}{extension}"
    target = settings.upload_dir / stored_name
    max_bytes = settings.max_video_size_mb * 1024 * 1024
    size = 0
    with target.open("wb") as output:
        while chunk := upload.file.read(CHUNK_BYTES):
            size += len(chunk)
            if size > max_bytes:
                output.close()
                target.unlink(missing_ok=True)
                raise AppError(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "VIDEO_TOO_LARGE",
                               f"Video exceeds {settings.max_video_size_mb} MB.", max_mb=settings.max_video_size_mb)
            output.write(chunk)
    if size == 0:
        target.unlink(missing_ok=True)
        raise AppError(status.HTTP_400_BAD_REQUEST, "EMPTY_FILE", "Empty file.")
    return original_name, stored_name, ALLOWED_FORMATS[extension], size


def video_out(video: Video) -> VideoOut:
    """The video plus whether its file is still on this server's disk.

    On hosts with an ephemeral disk (Render free plan) uploaded files disappear on every restart or
    redeploy. The analyses already made are kept in the database; only a NEW real analysis needs the
    file, so the app tells the user and offers to upload it again."""
    out = VideoOut.model_validate(video)
    out.file_available = video_file_path(video).is_file()
    return out


@router.post("/matches/{match_id}/videos", response_model=VideoOut, status_code=status.HTTP_201_CREATED)
def upload_video(match_id: str, video: UploadFile = File(...), user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.CONTRIBUTE)
    original_name, stored_name, video_format, size = _store_upload(video)
    entity = Video(match_id=match_id, file_name=original_name, file_path=stored_name, format=video_format, file_size=size)
    db.add(entity)
    db.commit()
    return video_out(entity)


@router.put("/videos/{video_id}/file", response_model=VideoOut)
def replace_video_file(video_id: str, video: UploadFile = File(...), user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Uploads the file of an existing video again (after the server lost it). Its analyses are kept."""
    entity = load_video(db, video_id, user, AccessLevel.CONTRIBUTE)
    if entity.status == "ANALYZING":
        raise AppError(status.HTTP_409_CONFLICT, "ANALYSIS_IN_PROGRESS", "Wait until the running analysis finishes.")
    original_name, stored_name, video_format, size = _store_upload(video)
    old_file = video_file_path(entity)
    entity.file_name, entity.file_path, entity.format, entity.file_size = original_name, stored_name, video_format, size
    db.commit()
    old_file.unlink(missing_ok=True)
    return video_out(entity)


@router.get("/matches/{match_id}/videos", response_model=list[VideoOut])
def list_videos(match_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.READ)
    return [video_out(video) for video in
            db.query(Video).filter(Video.match_id == match_id).order_by(Video.uploaded_at.desc())]


@router.get("/videos/{video_id}", response_model=VideoOut)
def get_video(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return video_out(load_video(db, video_id, user, AccessLevel.READ))


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    video = load_video(db, video_id, user, AccessLevel.MANAGE)
    if video.status == "ANALYZING":
        raise AppError(status.HTTP_409_CONFLICT, "ANALYSIS_IN_PROGRESS", "Cancel the running analysis first.")
    video_file_path(video).unlink(missing_ok=True)
    db.delete(video)
    db.commit()


@router.post("/videos/{video_id}/analysis", response_model=VideoAnalysisOut, status_code=status.HTTP_202_ACCEPTED)
def start_analysis(video_id: str, body: AnalysisRequest, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    video = load_video(db, video_id, user, AccessLevel.CONTRIBUTE)
    try:
        analysis, position = get_analysis_facade().request_analysis(db, video, body.model_dump())
    except AnalysisRequestError as error:
        raise AppError(status.HTTP_409_CONFLICT, error.code, str(error)) from error
    result = VideoAnalysisOut.model_validate(db.get(VideoAnalysis, analysis.id))
    result.queue_position = position or None
    return result


@router.get("/videos/{video_id}/analyses", response_model=list[VideoAnalysisOut])
def list_analyses(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_video(db, video_id, user, AccessLevel.READ)
    return (db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id)
              .order_by(VideoAnalysis.started_at.desc().nulls_first()).all())
