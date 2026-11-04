"""Clip library: every analysed clip of the team, to study them by situation, problem or strength.

It reuses what already exists (videos, their latest completed analysis, the reviewed problems and
strengths): nothing is copied. For each clip it lists only what concerns our team (the same rule as
the match plan) and the review state of each item, so the staff can tell what a person confirmed
from what the AI proposed.

The filters are an inverted index built with the HashTable of data_structures.py: one key per
situation, per problem and per strength, whose value is the list of clips that have it. Filtering by
"clips with low compactness" is then one lookup, O(1) on average, instead of scanning every clip;
the length of each list is the count shown next to each filter. The lists are sent with the facets,
so the app combines several filters by intersecting them.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from data_structures import HashTable
from models import AIRecommendation, AnalysisStrength, Match, RecommendationIndicator, TacticalIndicator, Video, VideoAnalysis
from services.match_plan import ISSUE_PREFIX, counts_for_us

NO_SITUATION = "NONE"


class ClipIndex:
    """Inverted index: facet value -> ids of the clips that have it (HashTable of lists)."""

    def __init__(self) -> None:
        self._index: HashTable[str, list[str]] = HashTable()

    def add(self, key: str, clip_id: str) -> None:
        clips = self._index.get(key)
        if clips is None:
            self._index.put(key, [clip_id])
        elif clips[-1] != clip_id:
            clips.append(clip_id)

    def clips(self, key: str) -> list[str]:
        return list(self._index.get(key) or [])

    def counts(self, prefix: str) -> list[dict]:
        rows = [{"key": key.removeprefix(prefix), "count": len(self._index.get(key) or []), "clips": self.clips(key)}
                for key in self._index.keys() if key.startswith(prefix)]
        return sorted(rows, key=lambda row: (-row["count"], row["key"]))


def latest_clip_analysis(db: Session, video_id: str) -> VideoAnalysis | None:
    """The clip's latest completed analysis: real first, simulated only if there is no real one."""
    analyses = (db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id, VideoAnalysis.status == "COMPLETED")
                  .order_by(VideoAnalysis.completed_at.desc()).all())
    real = [a for a in analyses if a.analysis_mode == "REAL_VIDEO_ANALYSIS"]
    return (real or analyses or [None])[0]


def _title(value: str) -> str:
    return value.removeprefix(ISSUE_PREFIX).capitalize()


def clip_library(db: Session, team_id: str) -> dict:
    rows = (db.query(Video, Match).join(Match, Match.id == Video.match_id)
              .filter(Match.team_id == team_id).order_by(Match.match_date.desc(), Video.uploaded_at.desc()).all())
    clips, index = [], ClipIndex()
    for video, match in rows:
        analysis = latest_clip_analysis(db, video.id)
        if analysis is None:
            continue
        recommendations = (db.query(AIRecommendation)
                             .join(RecommendationIndicator, RecommendationIndicator.recommendation_id == AIRecommendation.id)
                             .join(TacticalIndicator, TacticalIndicator.id == RecommendationIndicator.indicator_id)
                             .filter(TacticalIndicator.video_analysis_id == analysis.id).distinct().all())
        problems = [{"title": _title(r.title), "severity": r.severity, "status": r.status, "team": r.team}
                    for r in recommendations if counts_for_us(r.team, analysis.own_team)]
        strengths = [{"title": s.title, "status": s.status, "team": s.team}
                     for s in db.query(AnalysisStrength).filter(AnalysisStrength.analysis_id == analysis.id)
                     if counts_for_us(s.team, analysis.own_team)]
        clip_id = video.id
        index.add(f"situation:{video.situation or NO_SITUATION}", clip_id)
        for problem in problems:
            if problem["status"] != "DISMISSED":
                index.add(f"problem:{problem['title']}", clip_id)
        for strength in strengths:
            if strength["status"] != "DISMISSED":
                index.add(f"strength:{strength['title']}", clip_id)
        clips.append({
            "video_id": video.id, "file_name": video.file_name, "situation": video.situation,
            "situation_note": video.situation_note,
            "match": {"id": match.id, "opponent": match.opponent, "match_date": match.match_date.isoformat()},
            "analysis": {"id": analysis.id, "mode": analysis.analysis_mode,
                         "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None,
                         "own_team_known": analysis.own_team is not None},
            "problems": problems, "strengths": strengths,
        })
    return {"clips": clips,
            "facets": {"situations": index.counts("situation:"), "problems": index.counts("problem:"),
                       "strengths": index.counts("strength:")}}
