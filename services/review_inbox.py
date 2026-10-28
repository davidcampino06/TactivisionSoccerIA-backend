"""Review inbox: everything of our team that still waits for a person, across all matches.

    problems   possible problems still open (GENERATED or REVIEWED), most urgent first: they come out
               of the same priority queue (binary heap) as the rest of the app (review_priority.py)
    strengths  strengths nobody has confirmed or dismissed yet, most confident first, newest first
    matches    the matches that have something pending, newest first, for the filter

Only items that can reach the match plan are listed: those of our team (the analysis knows which
detected team is ours) and match-level ones; when the analysis does not know it, all of them. The
rival's items stay in each analysis, where they can still be read.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models import AIRecommendation, AnalysisStrength, Match, RecommendationIndicator, TacticalIndicator, Video, VideoAnalysis
from services.match_plan import counts_for_us
from services.review_priority import OPEN_STATES, by_priority


def _context(match: Match, analysis: VideoAnalysis | None) -> dict:
    return {"match_id": match.id, "opponent": match.opponent, "match_date": match.match_date,
            "analysis_id": analysis.id if analysis else None,
            "team_a_color": analysis.team_a_color if analysis else None,
            "team_b_color": analysis.team_b_color if analysis else None,
            "own_team": analysis.own_team if analysis else None}


def open_problems(db: Session, team_id: str) -> tuple[list[tuple[AIRecommendation, dict]], int]:
    """Ours, most urgent first, and how many open ones are the rival's (left in their analyses)."""
    rows = (db.query(AIRecommendation, Match).join(Match, Match.id == AIRecommendation.match_id)
              .filter(Match.team_id == team_id, AIRecommendation.status.in_(OPEN_STATES)).all())
    if not rows:
        return [], 0
    match_of = {recommendation.id: match for recommendation, match in rows}
    analysis_ids = dict(
        db.query(RecommendationIndicator.recommendation_id, TacticalIndicator.video_analysis_id)
          .join(TacticalIndicator, TacticalIndicator.id == RecommendationIndicator.indicator_id)
          .filter(RecommendationIndicator.recommendation_id.in_(match_of)).all())
    analyses = {a.id: a for a in db.query(VideoAnalysis).filter(VideoAnalysis.id.in_(set(analysis_ids.values()))).all()}
    result, rival = [], 0
    for recommendation in by_priority(recommendation for recommendation, _ in rows):
        analysis = analyses.get(analysis_ids.get(recommendation.id))
        if counts_for_us(recommendation.team, analysis.own_team if analysis else None):
            result.append((recommendation, _context(match_of[recommendation.id], analysis)))
        else:
            rival += 1
    return result, rival


def unreviewed_strengths(db: Session, team_id: str) -> list[tuple[AnalysisStrength, dict]]:
    rows = (db.query(AnalysisStrength, VideoAnalysis, Match)
              .join(VideoAnalysis, VideoAnalysis.id == AnalysisStrength.analysis_id)
              .join(Video, Video.id == VideoAnalysis.video_id)
              .join(Match, Match.id == Video.match_id)
              .filter(Match.team_id == team_id, AnalysisStrength.status == "GENERATED")
              .order_by(AnalysisStrength.confidence.desc(), AnalysisStrength.created_at.desc(), AnalysisStrength.id)
              .all())
    return [(strength, _context(match, analysis)) for strength, analysis, match in rows
            if counts_for_us(strength.team, analysis.own_team)]


def inbox_matches(problems: list[tuple[object, dict]], strengths: list[tuple[object, dict]]) -> list[dict]:
    matches: dict[str, dict] = {}
    for kind, items in (("problems", problems), ("strengths", strengths)):
        for _, context in items:
            entry = matches.setdefault(context["match_id"], {
                "match_id": context["match_id"], "opponent": context["opponent"],
                "match_date": context["match_date"], "problems": 0, "strengths": 0})
            entry[kind] += 1
    return sorted(matches.values(), key=lambda m: m["match_date"], reverse=True)
