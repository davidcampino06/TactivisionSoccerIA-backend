"""Video upload and analysis requests (Frontend -> Backend; never Frontend -> AI Service)."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from errors import AppError
from dependencies import AccessLevel, get_current_user, load_match, load_team, load_video
from models import User, Video, VideoAnalysis
import rls
from security import (
    PLAYBACK_TOKEN_MINUTES, InvalidTokenError, create_playback_token, decode_playback_token,
)
from schemas import AnalysisRequest, ClipCheckOut, VideoAnalysisOut, VideoOut, VideoSituationUpdate
from services.ai_client import AIServiceError, HttpClipCheckClient
from services.clip_library import clip_library
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
def upload_video(match_id: str, video: UploadFile = File(...), situation: str | None = Form(None),
                 situation_note: str | None = Form(None), situation_custom: str | None = Form(None),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_match(db, match_id, user, AccessLevel.CONTRIBUTE)
    tag = _situation(situation or None, situation_note, situation_custom)
    original_name, stored_name, video_format, size = _store_upload(video)
    entity = Video(match_id=match_id, file_name=original_name, file_path=stored_name, format=video_format, file_size=size,
                   situation=tag.situation, situation_note=tag.situation_note, situation_custom=tag.situation_custom)
    db.add(entity)
    db.commit()
    return video_out(entity)


def _situation(situation: str | None, note: str | None, custom: str | None) -> VideoSituationUpdate:
    try:
        return VideoSituationUpdate(situation=situation, situation_note=note, situation_custom=custom)
    except ValidationError as error:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_SITUATION", "Invalid situation or note.") from error


@router.patch("/videos/{video_id}", response_model=VideoOut)
def classify_video(video_id: str, body: VideoSituationUpdate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Says which tactical situation the clip shows (a person chooses it; the AI never does)."""
    entity = load_video(db, video_id, user, AccessLevel.CONTRIBUTE)
    entity.situation, entity.situation_note = body.situation, body.situation_note
    entity.situation_custom = body.situation_custom
    db.commit()
    return video_out(entity)


@router.get("/teams/{team_id}/clip-library")
def team_clip_library(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Every analysed clip of the team with its situation, problems and strengths (ours) and the
    counts per situation, problem and strength, from an inverted index (HashTable)."""
    load_team(db, team_id, user, AccessLevel.READ)
    return clip_library(db, team_id)


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


# What each stored format is served as. Browsers play MP4 (H.264) and WebM; the others are served
# with their real type and the app says so when the browser cannot play them.
MEDIA_TYPES = {"MP4": "video/mp4", "WEBM": "video/webm", "MOV": "video/quicktime", "AVI": "video/x-msvideo",
               "MKV": "video/x-matroska"}


@router.post("/videos/{video_id}/playback")
def video_playback_link(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A temporary link to watch the uploaded video again (with the analysis drawn on top, in the app).

    The link only plays this video and expires; whoever asks must be able to see the match."""
    video = load_video(db, video_id, user, AccessLevel.READ)
    if not video_file_path(video).is_file():
        raise AppError(status.HTTP_409_CONFLICT, "VIDEO_FILE_MISSING", "The video file is no longer on the server.")
    token = create_playback_token(user.id, video.id)
    return {"url": f"/api/videos/{video.id}/stream?token={token}", "media_type": MEDIA_TYPES.get(video.format, "video/mp4"),
            "expires_in_seconds": PLAYBACK_TOKEN_MINUTES * 60}


@router.get("/videos/{video_id}/stream", response_class=FileResponse)
def stream_video(video_id: str, token: str = Query(min_length=10, max_length=2000), db: Session = Depends(get_db)):
    """Plays the video (byte ranges supported, so the player can jump). Access is the playback link:
    it must be for this video, not expired, and its user must still be active and see the match."""
    try:
        payload = decode_playback_token(token)
    except InvalidTokenError as error:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "SESSION_EXPIRED", str(error)) from error
    user = db.get(User, payload.get("sub"))
    if payload.get("vid") != video_id or user is None or not user.is_active:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "SESSION_EXPIRED", "Invalid playback link.")
    rls.identify_user(db, user)
    video = load_video(db, video_id, user, AccessLevel.READ)
    path = video_file_path(video)
    if not path.is_file():
        raise AppError(status.HTTP_409_CONFLICT, "VIDEO_FILE_MISSING", "The video file is no longer on the server.")
    return FileResponse(path, media_type=MEDIA_TYPES.get(video.format, "application/octet-stream"),
                        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


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


@router.post("/videos/{video_id}/quality", response_model=ClipCheckOut)
def check_clip(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Asks the AI whether the clip is fit for the analysis and how much of it each detail covers.

    Advice only: it is not stored and never blocks an analysis."""
    video = load_video(db, video_id, user, AccessLevel.CONTRIBUTE)
    path = video_file_path(video)
    if not path.is_file():
        raise AppError(status.HTTP_409_CONFLICT, "VIDEO_FILE_MISSING",
                       "The video file is not available on the server; upload it again.")
    try:
        return HttpClipCheckClient().check(path)
    except AIServiceError as error:
        raise AppError(status.HTTP_503_SERVICE_UNAVAILABLE, "AI_UNAVAILABLE", error.user_message) from error


@router.get("/videos/{video_id}/analyses", response_model=list[VideoAnalysisOut])
def list_analyses(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_video(db, video_id, user, AccessLevel.READ)
    return (db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id)
              .order_by(VideoAnalysis.started_at.desc().nulls_first()).all())
