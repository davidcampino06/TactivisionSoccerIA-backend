"""Administrator: delete a whole team, or a single account. Permanent: there is no undo.

Deleting a team removes everything that belongs to it and the accounts of its people:

    team  -> players, matches (events, plays, formations), videos -> analyses -> detections, indicators,
             possible issues, strengths, track photos, links and labels, reports, crest   (ON DELETE CASCADE)
          -> the coach and the analysts of the team (their notifications go with them)
          -> the video files on the server disk

The database does the cascade: every table that belongs to a team references it with ON DELETE CASCADE
(TactiSoccerIA-db), so nothing is left behind and nothing has to be listed here. Rows written by a
deleted person in other places keep existing with the author set to NULL (ON DELETE SET NULL).

Row-Level Security does not let the administrator see a team's content, so the counts and the delete
run inside ``rls.bypass``. A team with an analysis still running cannot be deleted: the worker would
keep writing results for rows that no longer exist.
"""

from __future__ import annotations

import logging

from fastapi import status
from sqlalchemy import delete, func
from sqlalchemy.orm import Session

import rls
from errors import AppError
from log_setup import security_log
from models import Match, Player, Team, User, UserRole, Video, VideoAnalysis
from services.analysis_facade import video_file_path

logger = logging.getLogger("tactivision.admin")

RUNNING = ("PENDING", "PROCESSING")


def remove_team(db: Session, team_id: str, admin: User) -> dict:
    with rls.bypass(db):
        team = db.get(Team, team_id)
        if team is None:
            raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Team not found.")
        team_videos = db.query(Video).join(Match, Match.id == Video.match_id).filter(Match.team_id == team_id)
        running = (team_videos.join(VideoAnalysis, VideoAnalysis.video_id == Video.id)
                   .filter(VideoAnalysis.status.in_(RUNNING)).count())
        if running:
            raise AppError(status.HTTP_409_CONFLICT, "TEAM_ANALYSIS_RUNNING",
                           "The team has an analysis in progress; wait for it to finish or cancel it first.")
        files = [video_file_path(video) for video in team_videos.all()]
        summary = {
            "team": team.name,
            "players": db.query(func.count(Player.id)).filter(Player.team_id == team_id).scalar() or 0,
            "matches": db.query(func.count(Match.id)).filter(Match.team_id == team_id).scalar() or 0,
            "videos": len(files),
        }
        members = {user_id for (user_id,) in db.query(User.id).filter(User.team_id == team_id)}
        members.add(team.coach_id)
        db.execute(delete(Team).where(Team.id == team_id))
        # Administrators are never deleted here, even if one were linked to the team by mistake.
        users = db.execute(delete(User).where(User.id.in_(members), User.role != UserRole.ADMINISTRATOR)).rowcount
    db.commit()

    removed = 0
    for path in files:
        try:
            if path.is_file():
                path.unlink()
                removed += 1
        except OSError:
            logger.warning("Could not delete the video file %s of a deleted team", path.name)
    security_log.warning("Admin %s deleted team=%s (%s): %s users, %s matches, %s videos",
                         admin.id, team_id, summary["team"], users, summary["matches"], summary["videos"])
    return {**summary, "users": users, "files_removed": removed}


def remove_user(db: Session, user_id: str, admin: User) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "User not found.")
    if user.role == UserRole.ADMINISTRATOR:
        raise AppError(status.HTTP_403_FORBIDDEN, "ADMIN_MANAGED_BY_CONFIG", "Administrator accounts are managed by configuration.")
    with rls.bypass(db):
        owns_team = db.query(Team.id).filter(Team.coach_id == user.id).first()
    if owns_team:
        raise AppError(status.HTTP_409_CONFLICT, "COACH_OWNS_TEAM",
                       "This coach owns a team: delete the team, which also deletes his account.")
    summary = {"email": user.email, "role": user.role}
    db.execute(delete(User).where(User.id == user_id))
    db.commit()
    security_log.warning("Admin %s deleted user=%s (%s)", admin.id, user_id, summary["role"])
    return summary
