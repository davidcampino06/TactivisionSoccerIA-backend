"""Reports (Builder) and exports (Bridge)."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import AccessLevel, get_current_user, load_analysis, load_match, load_report, load_team
from models import Match, Report, User
from schemas import ReportCreate, ReportDetailOut, ReportOut
from services.match_timeline import ComparisonError
from services.reports import ReportDirector, ReportError, export_report, save_report

router = APIRouter(prefix="/api", tags=["Reports"])


@router.post("/teams/{team_id}/reports", response_model=ReportDetailOut, status_code=status.HTTP_201_CREATED)
def generate_report(team_id: str, body: ReportCreate, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    team = load_team(db, team_id, user, AccessLevel.CONTRIBUTE)
    director = ReportDirector(db)
    try:
        if body.report_type == "MATCH":
            if not body.match_id:
                raise ReportError("match_id is required for MATCH reports.")
            match = load_match(db, body.match_id, user, AccessLevel.READ)
            title = body.title or f"Match report vs {match.opponent}"
            snapshot = director.match_report(team, user, title, match)
        elif body.report_type == "VIDEO_ANALYSIS":
            if not body.analysis_id:
                raise ReportError("analysis_id is required for VIDEO_ANALYSIS reports.")
            analysis = load_analysis(db, body.analysis_id, user, AccessLevel.READ)
            match = db.get(Match, analysis.video.match_id)
            title = body.title or f"Video analysis vs {match.opponent}"
            snapshot = director.analysis_report(team, user, title, analysis)
        else:
            title = body.title or f"Team evolution - {team.name}"
            snapshot = director.evolution_report(team, user, title, body.match_ids)
    except (ReportError, ComparisonError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    report = save_report(db, team, user, body.report_type, title, snapshot)
    db.commit()
    return ReportDetailOut(**ReportOut.model_validate(report).model_dump(), snapshot=snapshot)


@router.get("/teams/{team_id}/reports", response_model=list[ReportOut])
def list_reports(team_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_team(db, team_id, user, AccessLevel.READ)
    return db.query(Report).filter(Report.team_id == team_id).order_by(Report.generated_at.desc()).all()


@router.get("/reports/{report_id}", response_model=ReportDetailOut)
def get_report(report_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = load_report(db, report_id, user, AccessLevel.READ)
    return ReportDetailOut(**ReportOut.model_validate(report).model_dump(), snapshot=json.loads(report.snapshot_data))


@router.get("/reports/{report_id}/export")
def export(report_id: str, format: str = Query(default="json"), user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    report = load_report(db, report_id, user, AccessLevel.READ)
    try:
        content, media_type, file_name = export_report(report, format.lower())
    except ReportError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    return Response(content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{file_name}"'})
