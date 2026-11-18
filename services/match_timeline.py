"""Match timeline (doubly linked list) + comparison and team evolution services.

Each match node knows its previous and next match chronologically, which is exactly what
"Analyze Team Evolution" needs (delta against the previous match) and what the UI needs
to navigate previous/next match.
"""

from __future__ import annotations

from collections import OrderedDict

import numpy as np
from sqlalchemy.orm import Session

from data_structures import DoublyLinkedList
from models import AIRecommendation, Match, TacticalIndicator, Video, VideoAnalysis
from errors import DomainError


class ComparisonError(DomainError):
    pass


# Indicators whose risk is a LOW value (the AI service flags them when value <= threshold).
# For every other indicator with a threshold the risk is a HIGH value (value >= threshold).
RISK_WHEN_LOW = {"team_width", "defensive_line_position", "network_average_links", "pressure_on_ball",
                 "attacking_width", "players_ahead_of_ball"}


def risk_direction(indicator_name: str) -> str:
    """'below' or 'above': which side of the threshold is a possible problem."""
    return "below" if indicator_name.split(".", 1)[-1] in RISK_WHEN_LOW else "above"


def change_percent(first: float | None, last: float | None) -> float | None:
    """Change from the first to the last match as a percentage of the first (None when it cannot be
    computed: a missing value or a first value of 0). It lets indicators of different units share a chart."""
    if first is None or last is None or abs(first) < 1e-9:
        return None
    return round((last - first) / abs(first) * 100, 1)


def change_assessment(name: str, first: float | None, last: float | None) -> str | None:
    """BETTER / WORSE / SAME from the first to the last match: moving away from the risky side of the
    indicator is better. Changes under 1 % of the first value count as the same."""
    if first is None or last is None:
        return None
    if abs(last - first) <= max(abs(first), 1e-9) * 0.01:
        return "SAME"
    towards_risk = (last > first) == (risk_direction(name) == "above")
    return "WORSE" if towards_risk else "BETTER"


def threshold_status(name: str, value: float | None, threshold: float | None) -> str | None:
    """EXCEEDS when the value is on the risky side of the threshold, OK otherwise, None without data."""
    if value is None or threshold is None:
        return None
    risky = value <= threshold if risk_direction(name) == "below" else value >= threshold
    return "EXCEEDS" if risky else "OK"


def assess_trend(name: str, trend: str, threshold: float | None) -> str | None:
    """Turns INCREASING / DECREASING into IMPROVING / WORSENING using the risk direction."""
    if threshold is None:
        return None
    if trend in ("STABLE", "INSUFFICIENT_DATA"):
        return trend
    moving_away_from_risk = (trend == "DECREASING") == (risk_direction(name) == "above")
    return "IMPROVING" if moving_away_from_risk else "WORSENING"


def _threshold_of(snapshots: list[dict], name: str) -> float | None:
    for snapshot in reversed(snapshots):
        threshold = snapshot["indicators"].get(name, {}).get("threshold")
        if threshold is not None:
            return threshold
    return None


class MatchTimeline:
    def __init__(self, matches: list[Match]) -> None:
        self._list: DoublyLinkedList[Match] = DoublyLinkedList()
        for match in sorted(matches, key=lambda m: m.match_date):
            self._list.append(match)

    @classmethod
    def for_team(cls, db: Session, team_id: str) -> "MatchTimeline":
        return cls(db.query(Match).filter(Match.team_id == team_id).all())

    def neighbors(self, match_id: str) -> tuple[Match | None, Match | None]:
        node = self._list.find(lambda m: m.id == match_id)
        if node is None:
            raise ComparisonError("Match not found in team timeline.", "NOT_FOUND")
        return (node.previous.value if node.previous else None, node.next.value if node.next else None)

    def nodes(self):
        node = self._list.head
        while node:
            yield node
            node = node.next

    def __len__(self) -> int:
        return len(self._list)


def latest_completed_analysis(db: Session, match_id: str) -> VideoAnalysis | None:
    """Prefers REAL_VIDEO_ANALYSIS; falls back to SIMULATION_MODE (always labelled)."""
    analyses = (db.query(VideoAnalysis).join(Video, Video.id == VideoAnalysis.video_id)
                  .filter(Video.match_id == match_id, VideoAnalysis.status == "COMPLETED")
                  .order_by(VideoAnalysis.completed_at.desc()).all())
    real = [a for a in analyses if a.analysis_mode == "REAL_VIDEO_ANALYSIS"]
    return (real or analyses or [None])[0]


def analysed_matches(db: Session, team_id: str) -> list[dict]:
    """Every team match with a completed analysis and the mode of the one used (real first)."""
    result = []
    for node in reversed(list(MatchTimeline.for_team(db, team_id).nodes())):
        analysis = latest_completed_analysis(db, node.value.id)
        if analysis:
            match = node.value
            result.append({"match_id": match.id, "opponent": match.opponent, "match_date": match.match_date.isoformat(),
                           "result": match.result, "analysis_id": analysis.id, "analysis_mode": analysis.analysis_mode})
    return result


def side_of(indicator_name: str, own_team: str | None) -> str:
    """The indicator name seen from the user's team: "team_b.team_width" -> "own.team_width" when the
    user's team was TEAM_B in that clip, "rival.team_width" when it was TEAM_A.

    The AI calls the two teams TEAM_A and TEAM_B in the order it finds them in each clip, so the same
    club can be A in one match and B in the next. Compared as they come, "Team A" across matches would
    mix the user's team with the rivals. When the analysis knows which one is ours (the kit colour
    given when analysing), the indicators are renamed to own / rival; otherwise they stay as they are."""
    prefix, _, rest = indicator_name.partition(".")
    if not rest or prefix not in ("team_a", "team_b") or own_team not in ("TEAM_A", "TEAM_B"):
        return indicator_name
    return f"{'own' if prefix == own_team.lower() else 'rival'}.{rest}"


def _match_snapshot(db: Session, match: Match) -> dict:
    analysis = latest_completed_analysis(db, match.id)
    indicators = {}
    own_team = analysis.own_team if analysis else None
    if analysis:
        for indicator in db.query(TacticalIndicator).filter(TacticalIndicator.video_analysis_id == analysis.id):
            indicators[side_of(indicator.name, own_team)] = {
                "value": indicator.value, "unit": indicator.unit, "threshold": indicator.threshold,
                "status": threshold_status(indicator.name, indicator.value, indicator.threshold),
            }
    recommendations = db.query(AIRecommendation).filter(AIRecommendation.match_id == match.id).all()
    return {
        "match_id": match.id,
        "opponent": match.opponent,
        "match_date": match.match_date.isoformat(),
        "result": match.result,
        "is_home": match.is_home,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "analysis_id": analysis.id if analysis else None,
        "analysis_mode": analysis.analysis_mode if analysis else None,
        # Which AI team was the user's in this clip (None when the kit colour was not given).
        "own_team": own_team,
        "indicators": indicators,
        "possible_issues": len([r for r in recommendations if r.status != "DISMISSED"]),
        "mean_issue_confidence": round(float(np.mean([r.confidence for r in recommendations])), 4) if recommendations else None,
    }


def _mode_warning(snapshots: list[dict]) -> list[str]:
    warnings = []
    modes = {s["analysis_mode"] for s in snapshots if s["analysis_mode"]}
    if "SIMULATION_MODE" in modes:
        warnings.append("Algunos partidos usan datos de MODO SIMULACIÓN; no los mezcles con conclusiones reales.")
    missing = [s["opponent"] for s in snapshots if not s["analysis_id"]]
    if missing:
        warnings.append(f"Partidos sin un análisis completado: {', '.join(missing)}.")
    unknown = [s["opponent"] for s in snapshots if s["analysis_id"] and not s.get("own_team")]
    if unknown and len(unknown) < len([s for s in snapshots if s["analysis_id"]]):
        warnings.append("No se sabe cuál es tu equipo en: " + ", ".join(unknown) + ". Sus indicadores quedan como "
                        "Equipo A / Equipo B; vuelve a analizar indicando el color de tu camiseta para compararlos.")
    return warnings


def _ordered_matches(db: Session, team_id: str, match_ids: list[str]) -> list[Match]:
    matches = db.query(Match).filter(Match.id.in_(match_ids), Match.team_id == team_id).all()
    if len(matches) != len(set(match_ids)):
        raise ComparisonError("All matches must exist and belong to the team.", "NOT_FOUND")
    return sorted(matches, key=lambda m: m.match_date)


def compare_matches(db: Session, team_id: str, match_ids: list[str]) -> dict:
    if len(set(match_ids)) < 2:
        raise ComparisonError("Select at least 2 matches to compare.", "COMPARE_MIN_MATCHES")
    snapshots = [_match_snapshot(db, match) for match in _ordered_matches(db, team_id, match_ids)]
    names = sorted({name for s in snapshots for name in s["indicators"]})
    rows = []
    for name in names:
        values = [s["indicators"].get(name, {}).get("value") for s in snapshots]
        known = [v for v in values if v is not None]
        rows.append({
            "indicator": name,
            "unit": next((s["indicators"][name]["unit"] for s in snapshots if name in s["indicators"]), None),
            "threshold": _threshold_of(snapshots, name),
            "risk_direction": risk_direction(name),
            "statuses": [s["indicators"].get(name, {}).get("status") for s in snapshots],
            "values": values,
            "difference_last_vs_first": round(values[-1] - values[0], 4) if values[0] is not None and values[-1] is not None else None,
            "change_percent": change_percent(values[0], values[-1]),
            "change_assessment": change_assessment(name, values[0], values[-1]),
            "range": round(max(known) - min(known), 4) if len(known) >= 2 else None,
        })
    return {"matches": snapshots, "indicators": rows, "warnings": _mode_warning(snapshots)}


def team_evolution(db: Session, team_id: str, match_ids: list[str] | None = None, last: int = 5) -> dict:
    timeline = MatchTimeline.for_team(db, team_id)
    selected = set(match_ids) if match_ids else None
    if selected is None:
        # Walk the timeline and keep the latest `last` matches that already have a completed
        # analysis: scheduled or unanalysed matches carry no indicators to plot.
        nodes = [node for node in timeline.nodes() if latest_completed_analysis(db, node.value.id)][-last:]
    else:
        nodes = [node for node in timeline.nodes() if node.value.id in selected]
    if len(nodes) < 3:
        raise ComparisonError("Team evolution needs at least 3 analysed matches.", "EVOLUTION_MIN_MATCHES")

    snapshots = [_match_snapshot(db, node.value) for node in nodes]
    series: OrderedDict[str, list] = OrderedDict()
    for name in sorted({n for s in snapshots for n in s["indicators"]}):
        series[name] = [s["indicators"].get(name, {}).get("value") for s in snapshots]

    trends = []
    for name, values in series.items():
        points = [(index, value) for index, value in enumerate(values) if value is not None]
        deltas = [round(values[i] - values[i - 1], 4) if values[i] is not None and values[i - 1] is not None else None
                  for i in range(1, len(values))]
        slope = None
        trend = "INSUFFICIENT_DATA"
        if len(points) >= 3:
            xs, ys = zip(*points)
            slope = round(float(np.polyfit(xs, ys, 1)[0]), 5)
            scale = max(abs(float(np.mean(ys))), 1e-6)
            trend = "STABLE" if abs(slope) / scale < 0.03 else ("INCREASING" if slope > 0 else "DECREASING")
        threshold = _threshold_of(snapshots, name)
        trends.append({
            "indicator": name, "values": values, "deltas_vs_previous": deltas, "slope": slope, "trend": trend,
            "unit": next((s["indicators"][name]["unit"] for s in snapshots if name in s["indicators"]), None),
            "threshold": threshold, "risk_direction": risk_direction(name),
            "assessment": assess_trend(name, trend, threshold),
        })

    return {"matches": snapshots, "trends": trends, "warnings": _mode_warning(snapshots)}
