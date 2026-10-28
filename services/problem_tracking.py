"""Follow-up of the confirmed problems: did they come back in the matches analysed after?

For every problem of our team that a person CONFIRMED in some match, the analysed matches from the
first confirmation onwards (oldest first) say what the analyses show, without guessing:

    CONFIRMED     the AI raised it again and a person confirmed it
    DETECTED      the AI raised it again; nobody has reviewed it yet
    DISMISSED     the AI raised it again and a person dismissed it
    NOT_DETECTED  the analysis judged the same indicator (enough frames) and did not raise it
    NOT_MEASURED  it could not be judged: the indicator was not measured (e.g. no attack direction),
                  it had fewer frames than the AI needs to raise a problem (the team hardly defended
                  in the clip, say), or the analysis is older than migration 0019 and did not store
                  how many frames it judged. Unknown, never counted as "it did not appear".

The trend only looks at the matches after the first confirmation where the indicator was measured:

    NO_DATA       none yet
    RECURRING     raised again in the last measured match
    GONE          not raised in any of them
    IMPROVING     not raised in the last one, but raised in some earlier one

Matches are ordered by date with the team's match timeline (doubly linked list, match_timeline.py).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from models import AIRecommendation, Match, RecommendationIndicator, RecommendationStatus, TacticalIndicator, VideoAnalysis
from services.match_plan import ISSUE_PREFIX, counts_for_us
from services.match_timeline import analysed_matches

RAISED = {RecommendationStatus.CONFIRMED: "CONFIRMED", RecommendationStatus.DISMISSED: "DISMISSED"}
MIN_SAMPLES = 8  # the AI does not raise a problem with fewer judged frames (ai/tactical_insights.py)


def _suffix(indicator_name: str) -> str:
    return indicator_name.split(".", 1)[-1]


def _prefixes(team: str | None, own_team: str | None) -> set[str]:
    """Indicator prefixes that measure this problem for our team in one analysis (both if unknown)."""
    if team == "MATCH":
        return {"match"}
    return {own_team.lower()} if own_team else {"team_a", "team_b"}


def problem_tracking(db: Session, team_id: str, before: datetime | None = None) -> list[dict]:
    """Every confirmed problem of our team with its follow-up, most recurring first."""
    matches = sorted((m for m in analysed_matches(db, team_id)
                      if before is None or m["match_date"] < before.isoformat()), key=lambda m: m["match_date"])
    if not matches:
        return []
    by_id = {m["match_id"]: m for m in matches}
    latest = {a.id: a for a in db.query(VideoAnalysis).filter(VideoAnalysis.id.in_([m["analysis_id"] for m in matches]))}

    recommendations = db.query(AIRecommendation).filter(AIRecommendation.match_id.in_(by_id)).all()
    links = (db.query(RecommendationIndicator.recommendation_id, TacticalIndicator.video_analysis_id, TacticalIndicator.name)
               .join(TacticalIndicator, TacticalIndicator.id == RecommendationIndicator.indicator_id)
               .filter(RecommendationIndicator.recommendation_id.in_([r.id for r in recommendations])).all()
             ) if recommendations else []
    analysis_of = {rec_id: analysis_id for rec_id, analysis_id, _ in links}
    indicators_of: dict[str, set[str]] = {}
    for rec_id, _, name in links:
        indicators_of.setdefault(rec_id, set()).add(_suffix(name))
    own = {a.id: a.own_team for a in db.query(VideoAnalysis).filter(VideoAnalysis.id.in_(set(analysis_of.values())))}

    # What the AI raised for our team in each match, by problem title (best state when raised twice).
    raised: dict[str, dict[str, str]] = {}
    measures: dict[str, set[str]] = {}
    team_of: dict[str, str | None] = {}
    rank = {"CONFIRMED": 3, "DETECTED": 2, "DISMISSED": 1}
    for recommendation in recommendations:
        if not counts_for_us(recommendation.team, own.get(analysis_of.get(recommendation.id))):
            continue
        state = RAISED.get(recommendation.status, "DETECTED")
        per_match = raised.setdefault(recommendation.title, {})
        if rank[state] > rank.get(per_match.get(recommendation.match_id, ""), 0):
            per_match[recommendation.match_id] = state
        measures.setdefault(recommendation.title, set()).update(indicators_of.get(recommendation.id, set()))
        team_of.setdefault(recommendation.title, recommendation.team)

    # Indicators each analysis could judge: stored with enough frames (NULL samples: unknown).
    judged_in = {m["analysis_id"]: {name for (name,) in db.query(TacticalIndicator.name)
                                     .filter(TacticalIndicator.video_analysis_id == m["analysis_id"],
                                             TacticalIndicator.samples >= MIN_SAMPLES)}
                 for m in matches}

    items = []
    for title, per_match in raised.items():
        confirmed = [m for m in matches if per_match.get(m["match_id"]) == "CONFIRMED"]
        if not confirmed:
            continue
        start = matches.index(confirmed[0])
        timeline = []
        for match in matches[start:]:
            state = per_match.get(match["match_id"])
            if state is None:
                analysis = latest[match["analysis_id"]]
                names = judged_in[match["analysis_id"]]
                prefixes = _prefixes(team_of[title], analysis.own_team)
                # Without knowing which detected team is ours, both must have been judged.
                judged = all(any(f"{prefix}.{suffix}" in names for suffix in measures.get(title, ())) for prefix in prefixes)
                state = "NOT_DETECTED" if judged else "NOT_MEASURED"
            timeline.append({"match_id": match["match_id"], "opponent": match["opponent"],
                             "match_date": match["match_date"], "analysis_id": match["analysis_id"], "state": state})
        after = [step for step in timeline[1:] if step["state"] != "NOT_MEASURED"]
        came_back = [step for step in after if step["state"] != "NOT_DETECTED"]
        if not after:
            trend = "NO_DATA"
        elif after[-1]["state"] != "NOT_DETECTED":
            trend = "RECURRING"
        elif came_back:
            trend = "IMPROVING"
        else:
            trend = "GONE"
        items.append({"title": title.removeprefix(ISSUE_PREFIX).capitalize(), "key": title, "trend": trend,
                      "first_confirmed": timeline[0], "timeline": timeline,
                      "measured_after": len(after), "came_back": len(came_back)})
    order = {"RECURRING": 0, "IMPROVING": 1, "NO_DATA": 2, "GONE": 3}
    return sorted(items, key=lambda i: (order[i["trend"]], -i["came_back"], i["title"]))
