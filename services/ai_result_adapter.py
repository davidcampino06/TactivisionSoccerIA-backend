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
"""

from __future__ import annotations

from models import AIRecommendation, RecommendationIndicator, TacticalIndicator, new_id, utc_now
from services.ai_client import AIAnalysisPayload

MAX_TEXT = 255


def _fit(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


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
            )
            recommendations.append(entity)
            for indicator_name in item.related_indicators:
                if indicator_name in self._indicator_ids:
                    links.append(RecommendationIndicator(
                        id=new_id(), recommendation_id=entity.id, indicator_id=self._indicator_ids[indicator_name]
                    ))
        return recommendations, links

    def warning_message(self) -> str | None:
        warnings = list(self._payload.warnings)
        # Simulated results must always say so (Spanish: this text is shown to the user).
        if self._payload.mode == "SIMULATION_MODE" and not any("SIMULACIÓN" in w.upper() for w in warnings):
            warnings.insert(0, "MODO SIMULACIÓN: datos sintéticos, no es un análisis de video real.")
        text = " | ".join(warnings)
        return _fit(text) if text.strip() else None

    def video_duration_seconds(self) -> int | None:
        duration = self._payload.video.get("duration_seconds")
        return int(round(duration)) if isinstance(duration, (int, float)) else None
