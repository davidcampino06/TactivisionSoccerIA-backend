"""Video analysis results: status, detections, tracks, indicators, player identification."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from dependencies import AccessLevel, get_current_user, load_analysis, load_player
from models import Detection, Match, TacticalIndicator, User
from routers.recommendations import recommendations_for_analysis
from schemas import AnalysisResultOut, DetectionOut, TacticalIndicatorOut, TrackAssignmentRequest, VideoAnalysisOut
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
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
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
    }


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
                     func.max(Detection.frame_number), func.avg(Detection.confidence), func.max(Detection.player_id))
              .filter(Detection.video_analysis_id == analysis_id, Detection.track_id.isnot(None))
              .group_by(Detection.track_id).order_by(Detection.track_id).all())
    return [
        {"track_id": track_id, "label": f"Player Track {track_id}", "detections": count, "first_frame": first,
         "last_frame": last, "mean_confidence": round(float(confidence), 4), "player_id": player_id}
        for track_id, count, first, last, confidence, player_id in rows
    ]


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
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Player belongs to another team.")
        player_number = player.shirt_number
    updated = (db.query(Detection)
                 .filter(Detection.video_analysis_id == analysis_id, Detection.track_id == track_id)
                 .update({Detection.player_id: body.player_id, Detection.player_number: player_number},
                         synchronize_session=False))
    if updated == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not found in this analysis.")
    db.commit()
    return {"track_id": track_id, "player_id": body.player_id, "detections_updated": updated}
