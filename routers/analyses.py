"""Video analysis results: status, detections, tracks, indicators, player identification."""

import json

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from errors import AppError, domain_error
from dependencies import AccessLevel, get_current_user, load_analysis, load_player
from models import AnalysisStrength, Detection, Match, TacticalIndicator, TrackSnapshot, User
from routers.recommendations import recommendations_for_analysis
from schemas import (
    AnalysisResultOut, DetectionOut, StrengthOut, StrengthStatusUpdate, TacticalIndicatorOut, TrackAssignmentRequest,
    VideoAnalysisOut,
)
from services.analysis_facade import get_analysis_facade
from services.analysis_state import InvalidStateTransition

router = APIRouter(prefix="/api/analyses", tags=["Video Analysis"])


def analysis_out(analysis) -> VideoAnalysisOut:
    data = VideoAnalysisOut.model_validate(analysis)
    if analysis.status == "PENDING":
        data.queue_position = get_analysis_facade().queue_position(analysis.id)
    return data


@router.get("/{analysis_id}", response_model=VideoAnalysisOut)
def get_analysis(analysis_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return analysis_out(load_analysis(db, analysis_id, user, AccessLevel.READ))


@router.post("/{analysis_id}/cancel", response_model=VideoAnalysisOut)
def cancel_analysis(analysis_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = load_analysis(db, analysis_id, user, AccessLevel.CONTRIBUTE)
    try:
        get_analysis_facade().cancel_analysis(db, analysis)
    except InvalidStateTransition as error:
        raise domain_error(error, status.HTTP_409_CONFLICT) from error
    return analysis_out(analysis)


@router.get("/{analysis_id}/result", response_model=AnalysisResultOut)
def get_result(analysis_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = load_analysis(db, analysis_id, user, AccessLevel.READ)
    counts = dict(db.query(Detection.object_type, func.count()).filter(Detection.video_analysis_id == analysis_id)
                    .group_by(Detection.object_type).all())
    frames = db.query(func.count(func.distinct(Detection.frame_number))).filter(
        Detection.video_analysis_id == analysis_id).scalar()
    tracks = db.query(func.count(func.distinct(Detection.track_id))).filter(
        Detection.video_analysis_id == analysis_id, Detection.track_id.isnot(None)).scalar()
    ball_frames = db.query(func.count(func.distinct(Detection.frame_number))).filter(
        Detection.video_analysis_id == analysis_id, Detection.object_type == "BALL").scalar()
    indicators = (db.query(TacticalIndicator).filter(TacticalIndicator.video_analysis_id == analysis_id)
                    .order_by(TacticalIndicator.name).all())
    return {
        "analysis": analysis_out(analysis),
        "label": "SIMULATION MODE" if analysis.analysis_mode == "SIMULATION_MODE" else "REAL VIDEO ANALYSIS",
        "summary": {
            "player_detections": counts.get("PLAYER", 0),
            "ball_detections": counts.get("BALL", 0),
            "frames_with_detections": frames,
            "player_tracks": tracks,
            "ball_detected": ball_frames > 0,
        },
        "indicators": indicators,
        "recommendations": recommendations_for_analysis(db, analysis_id),
        "strengths": (db.query(AnalysisStrength).filter(AnalysisStrength.analysis_id == analysis_id)
                        .order_by(AnalysisStrength.confidence.desc(), AnalysisStrength.title).all()),
        "proximity_network": json.loads(analysis.proximity_network) if analysis.proximity_network else None,
    }


@router.patch("/{analysis_id}/strengths/{strength_id}", response_model=StrengthOut)
def review_strength(analysis_id: str, strength_id: str, body: StrengthStatusUpdate,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A person confirms or dismisses what the AI says the team did well (migration 0018).

    Only from GENERATED, like the problems: the match plan uses the confirmed ones."""
    load_analysis(db, analysis_id, user, AccessLevel.CONTRIBUTE)
    strength = db.get(AnalysisStrength, strength_id)
    if strength is None or strength.analysis_id != analysis_id:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Strength not found.")
    if strength.status != "GENERATED":
        raise AppError(status.HTTP_409_CONFLICT, "INVALID_STRENGTH_STATE",
                       f"Cannot {body.action} a {strength.status} strength.")
    strength.status = "CONFIRMED" if body.action == "confirm" else "DISMISSED"
    db.commit()
    return strength


@router.get("/{analysis_id}/indicators", response_model=list[TacticalIndicatorOut])
def list_indicators(analysis_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_analysis(db, analysis_id, user, AccessLevel.READ)
    return (db.query(TacticalIndicator).filter(TacticalIndicator.video_analysis_id == analysis_id)
              .order_by(TacticalIndicator.name).all())


@router.get("/{analysis_id}/detections", response_model=list[DetectionOut])
def list_detections(
    analysis_id: str,
    object_type: str | None = Query(default=None, pattern="^(PLAYER|BALL)$"),
    track_id: int | None = None,
    frame_from: int | None = Query(default=None, ge=0),
    frame_to: int | None = Query(default=None, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    load_analysis(db, analysis_id, user, AccessLevel.READ)
    query = db.query(Detection).filter(Detection.video_analysis_id == analysis_id)
    if object_type:
        query = query.filter(Detection.object_type == object_type)
    if track_id is not None:
        query = query.filter(Detection.track_id == track_id)
    if frame_from is not None:
        query = query.filter(Detection.frame_number >= frame_from)
    if frame_to is not None:
        query = query.filter(Detection.frame_number <= frame_to)
    return query.order_by(Detection.frame_number, Detection.track_id).offset(offset).limit(limit).all()


@router.get("/{analysis_id}/tracks")
def list_tracks(analysis_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_analysis(db, analysis_id, user, AccessLevel.READ)
    rows = (db.query(Detection.track_id, func.count(), func.min(Detection.frame_number),
                     func.max(Detection.frame_number), func.avg(Detection.confidence), func.max(Detection.player_id),
                     func.min(Detection.timestamp), func.max(Detection.timestamp))
              .filter(Detection.video_analysis_id == analysis_id, Detection.track_id.isnot(None))
              .group_by(Detection.track_id).order_by(Detection.track_id).all())
    photos = {track_id: seconds for track_id, seconds in
              db.query(TrackSnapshot.track_id, TrackSnapshot.timestamp).filter(TrackSnapshot.analysis_id == analysis_id)}
    return [
        {"track_id": track_id, "label": f"Trayectoria {track_id}", "detections": count, "first_frame": first,
         "last_frame": last, "mean_confidence": round(float(confidence), 4), "player_id": player_id,
         "first_seconds": float(first_seconds), "last_seconds": float(last_seconds),
         "has_snapshot": track_id in photos,
         "snapshot_seconds": float(photos[track_id]) if track_id in photos else None}
        for track_id, count, first, last, confidence, player_id, first_seconds, last_seconds in rows
    ]


@router.get("/{analysis_id}/tracks/{track_id}/snapshot", response_class=Response,
            responses={200: {"content": {"image/jpeg": {}}}})
def track_snapshot(analysis_id: str, track_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """The photo of a track (best crop of the video): what the staff looks at to tell who is who.

    Analyses made before migration 0021 have no photos: 404, and the app shows the track without one."""
    load_analysis(db, analysis_id, user, AccessLevel.READ)
    snapshot = db.get(TrackSnapshot, (analysis_id, track_id))
    if snapshot is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "This track has no photo.")
    # A photo never changes once the analysis is saved: the browser can keep it (private: it is a team's data).
    return Response(content=snapshot.image, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@router.get("/{analysis_id}/overlay")
def analysis_overlay(analysis_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """What the AI saw in each analysed frame, to draw it over the video while it plays.

    ``frames`` is ordered by time; each one is [seconds, boxes] and each box is
    [x, y, width, height, track id or null, "P" player / "B" ball / "O" other], in pixels of the
    original video. ``interval`` is the usual time between analysed frames (the AI samples the video),
    and ``until`` the last second analysed: after it the video has no boxes."""
    load_analysis(db, analysis_id, user, AccessLevel.READ)
    rows = (db.query(Detection.timestamp, Detection.bounding_box_x, Detection.bounding_box_y,
                     Detection.bounding_box_width, Detection.bounding_box_height, Detection.track_id,
                     Detection.object_type)
              .filter(Detection.video_analysis_id == analysis_id)
              .order_by(Detection.timestamp, Detection.track_id).all())
    kinds = {"PLAYER": "P", "BALL": "B"}
    frames: list[list] = []
    for seconds, x, y, width, height, track_id, object_type in rows:
        seconds = float(seconds)
        if not frames or frames[-1][0] != seconds:
            frames.append([seconds, []])
        frames[-1][1].append([float(x), float(y), float(width), float(height), track_id, kinds.get(object_type, "O")])
    gaps = sorted(round(b[0] - a[0], 4) for a, b in zip(frames, frames[1:]))
    return {"frames": frames, "interval": gaps[len(gaps) // 2] if gaps else 0.0,
            "until": frames[-1][0] if frames else 0.0}


@router.put("/{analysis_id}/tracks/{track_id}/player")
def assign_track_to_player(analysis_id: str, track_id: int, body: TrackAssignmentRequest,
                           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Use case "Correct Player Identification": a human links a temporary track to a squad player.
    No biometric recognition is performed."""
    analysis = load_analysis(db, analysis_id, user, AccessLevel.CONTRIBUTE)
    player_number = None
    if body.player_id:
        player = load_player(db, body.player_id, user, AccessLevel.READ)
        match = db.get(Match, analysis.video.match_id)
        if player.team_id != match.team_id:
            raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Player belongs to another team.")
        player_number = player.shirt_number
    updated = (db.query(Detection)
                 .filter(Detection.video_analysis_id == analysis_id, Detection.track_id == track_id)
                 .update({Detection.player_id: body.player_id, Detection.player_number: player_number},
                         synchronize_session=False))
    if updated == 0:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Track not found in this analysis.")
    db.commit()
    return {"track_id": track_id, "player_id": body.player_id, "detections_updated": updated}
