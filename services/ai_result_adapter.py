"""Adapter pattern: converts the AI Service JSON contract into ERD entities.

The AI Service speaks "possible issues + recommendations + indicators" while the
database speaks ``detections``, ``tactical_indicators``, ``ai_recommendations`` and
``recommendation_indicators``. This class is the only place that knows both formats.

Mapping of a recommendation to ``ai_recommendations``:
    title       <- possible issue ("Possible tactical issue: ...")
    description <- recommendation text
    evidence    <- numeric evidence
    confidence  <- confidence (0..1)
    severity    <- LOW / MEDIUM / HIGH

What the team did well (``strengths``) goes to ``analysis_strengths``, one row per strength with
its explanation as JSON, like the recommendations.

The proximity network (graph + BFS of the AI) is kept whole as JSON in
``video_analyses.proximity_network``: it is only read to draw it.
"""

from __future__ import annotations

import json
import re

from models import AIRecommendation, AnalysisStrength, RecommendationIndicator, TacticalIndicator, new_id, utc_now
from services.ai_client import AIAnalysisPayload
from services.analysis_state import MAX_WARNING_LENGTH

MAX_TEXT = 255
# Explanation JSON: three short texts plus one frame (about 2 KB); anything far bigger is not kept.
MAX_EXPLANATION_CHARS = 20_000
EXPLANATION_TEXTS = ("seen", "meaning", "coach", "keep")  # "keep": how to keep doing a strength
HEX_COLOR = re.compile(r"^#[0-9a-f]{6}$")


def _fit(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def explanation_json(explanation: dict | None) -> str | None:
    """The explanation as JSON, with only the known fields; None if it is missing or malformed.

    If the example frame makes it too big, the texts are kept without the frame."""
    if not isinstance(explanation, dict) or not isinstance(explanation.get("seen"), str):
        return None
    kept = {key: explanation[key][:MAX_TEXT * 4] for key in EXPLANATION_TEXTS if isinstance(explanation.get(key), str)}
    example = explanation.get("example")
    kept["example"] = example if isinstance(example, dict) else None
    text = json.dumps(kept, ensure_ascii=False, separators=(",", ":"))
    if len(text) > MAX_EXPLANATION_CHARS:
        kept["example"] = None
        text = json.dumps(kept, ensure_ascii=False, separators=(",", ":"))
    return text


class AIResultAdapter:
    def __init__(self, payload: AIAnalysisPayload, analysis_id: str, match_id: str) -> None:
        self._payload = payload
        self._analysis_id = analysis_id
        self._match_id = match_id
        self._indicator_ids: dict[str, str] = {}

    def detection_rows(self) -> list[dict]:
        """Plain dicts for a fast bulk INSERT (detections can be thousands of rows)."""
        return [
            {
                "id": new_id(),
                "video_analysis_id": self._analysis_id,
                "frame_number": item.frame_number,
                "timestamp": round(item.timestamp, 4),
                "object_type": item.object_type,
                "confidence": round(item.confidence, 4),
                "bounding_box_x": round(item.bounding_box_x, 4),
                "bounding_box_y": round(item.bounding_box_y, 4),
                "bounding_box_width": round(item.bounding_box_width, 4),
                "bounding_box_height": round(item.bounding_box_height, 4),
                "track_id": item.track_id,
                "player_id": None,
                "player_number": None,
            }
            for item in self._payload.detections
        ]

    def indicators(self) -> list[TacticalIndicator]:
        calculated_at = utc_now()
        entities = []
        for item in self._payload.tactical_indicators:
            entity = TacticalIndicator(
                id=new_id(),
                video_analysis_id=self._analysis_id,
                name=_fit(item.name),
                value=round(item.value, 4),
                unit=item.unit[:50],
                threshold=round(item.threshold, 4) if item.threshold is not None else None,
                calculated_at=calculated_at,
            )
            self._indicator_ids[item.name] = entity.id
            entities.append(entity)
        return entities

    def recommendations(self) -> tuple[list[AIRecommendation], list[RecommendationIndicator]]:
        """Call after ``indicators()`` so the links can be resolved."""
        recommendations, links = [], []
        for item in self._payload.recommendations:
            entity = AIRecommendation(
                id=new_id(),
                match_id=self._match_id,
                title=_fit(item.title),
                description=_fit(item.recommendation),
                severity=item.severity,
                confidence=round(item.confidence, 4),
                evidence=_fit(item.evidence),
                team=item.team,
                explanation=explanation_json(item.explanation),
            )
            recommendations.append(entity)
            for indicator_name in item.related_indicators:
                if indicator_name in self._indicator_ids:
                    links.append(RecommendationIndicator(
                        id=new_id(), recommendation_id=entity.id, indicator_id=self._indicator_ids[indicator_name]
                    ))
        return recommendations, links

    def strengths(self) -> list[AnalysisStrength]:
        return [
            AnalysisStrength(
                id=new_id(),
                analysis_id=self._analysis_id,
                team=item.team,
                code=item.code,
                title=_fit(item.title),
                evidence=item.evidence[:MAX_TEXT * 4],
                confidence=round(item.confidence, 4),
                indicator=item.related_indicators[0][:100] if item.related_indicators else None,
                explanation=explanation_json(item.explanation),
            )
            for item in self._payload.strengths
        ]

    def warning_message(self) -> str | None:
        warnings = list(self._payload.warnings)
        # Simulated results must always say so (Spanish: this text is shown to the user).
        if self._payload.mode == "SIMULATION_MODE" and not any("SIMULACIÓN" in w.upper() for w in warnings):
            warnings.insert(0, "MODO SIMULACIÓN: datos sintéticos, no es un análisis de video real.")
        text = " | ".join(warnings)
        return text[:MAX_WARNING_LENGTH] if text.strip() else None

    def own_team(self) -> str | None:
        """Which detected team wears the kit colour given for this analysis (None if unknown)."""
        value = self._payload.teams.get("own_team")
        return value if value in ("TEAM_A", "TEAM_B") else None

    def team_colors(self) -> tuple[str | None, str | None]:
        """Shirt colour of TEAM_A and TEAM_B (#rrggbb), or None when the AI did not give a valid one."""
        colors = self._payload.teams.get("colors") or {}
        found = []
        for team in ("TEAM_A", "TEAM_B"):
            value = colors.get(team) if isinstance(colors, dict) else None
            value = value.lower() if isinstance(value, str) else None
            found.append(value if value and HEX_COLOR.match(value) else None)
        return found[0], found[1]

    def video_duration_seconds(self) -> int | None:
        duration = self._payload.video.get("duration_seconds")
        return int(round(duration)) if isinstance(duration, (int, float)) else None

    def proximity_network_json(self) -> str | None:
        network = self._payload.proximity_network
        return json.dumps(network.model_dump(), separators=(",", ":")) if network else None
