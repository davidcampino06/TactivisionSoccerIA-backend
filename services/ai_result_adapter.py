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

The identification hints go to ``track_links`` (tracks that look like one player cut in two) and
``track_role_suggestions`` (kits of no team). Like the photos, each one is checked on its own and a
bad one is skipped: they are hints, the analysis is worth more.
"""

from __future__ import annotations

import base64
import binascii
import json
import re

from models import (
    AIRecommendation, AnalysisStrength, RecommendationIndicator, TacticalIndicator, TrackLink, TrackRoleSuggestion,
    TrackSnapshot, new_id, utc_now,
)
from pydantic import ValidationError

from services.ai_client import AIAnalysisPayload, RoleSuggestionPayload, SnapshotPayload, TrackLinkPayload
from services.analysis_state import MAX_WARNING_LENGTH

MAX_TEXT = 255
# A photo of a track is a small JPEG (the AI scales it to 160 px high): 60 000 bytes is the table's limit.
MAX_SNAPSHOT_BYTES = 60_000
JPEG_MAGIC = b"\xff\xd8\xff"
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

    def track_snapshots(self) -> list[TrackSnapshot]:
        """One photo per track that has detections. A photo that is not a small JPEG is skipped: the
        analysis is worth more than its photos, so a bad one never fails it."""
        tracks = self._tracks()
        rows = []
        for raw in self._payload.track_snapshots:
            try:
                item = SnapshotPayload.model_validate(raw)
                image = base64.b64decode(item.image_jpeg_base64, validate=True)
            except (ValidationError, binascii.Error, ValueError):
                continue
            if item.track_id not in tracks:
                continue
            if not image.startswith(JPEG_MAGIC) or len(image) > MAX_SNAPSHOT_BYTES:
                continue
            rows.append(TrackSnapshot(
                analysis_id=self._analysis_id, track_id=item.track_id, frame_number=item.frame_number,
                timestamp=round(item.timestamp, 4), confidence=round(item.confidence, 4),
                width=item.width, height=item.height, image=image))
        return rows

    def _tracks(self) -> set[int]:
        return {item.track_id for item in self._payload.detections if item.track_id is not None}

    def track_links(self) -> list[TrackLink]:
        """The suggested links between tracks of this analysis. Skipped: a link that does not validate,
        names a track without detections, goes back in time, or uses a track already used (one to one)."""
        tracks = self._tracks()
        raw_links = self._payload.track_links.get("links", []) if isinstance(self._payload.track_links, dict) else []
        rows, ends, starts = [], set(), set()
        for raw in raw_links[:300]:
            try:
                item = TrackLinkPayload.model_validate(raw)
            except ValidationError:
                continue
            if item.from_track == item.to_track or not {item.from_track, item.to_track} <= tracks:
                continue
            if item.to_first_frame <= item.from_last_frame or item.from_track in ends or item.to_track in starts:
                continue
            ends.add(item.from_track)
            starts.add(item.to_track)
            rows.append(TrackLink(
                analysis_id=self._analysis_id, from_track=item.from_track, to_track=item.to_track,
                from_last_frame=item.from_last_frame, to_first_frame=item.to_first_frame,
                gap_seconds=round(item.gap_seconds, 3), distance_heights=round(item.distance_heights, 3),
                color_distance=None if item.color_distance is None else round(item.color_distance, 2),
                same_team=item.same_team, confidence=round(item.confidence, 3), status="SUGGESTED"))
        return rows

    def track_role_suggestions(self) -> list[TrackRoleSuggestion]:
        """Possible referees and goalkeepers, one per track with detections (a repeated track is skipped)."""
        tracks = self._tracks()
        rows, seen = [], set()
        for raw in self._payload.track_role_suggestions:
            try:
                item = RoleSuggestionPayload.model_validate(raw)
            except ValidationError:
                continue
            if item.track_id not in tracks or item.track_id in seen:
                continue
            seen.add(item.track_id)
            rows.append(TrackRoleSuggestion(
                analysis_id=self._analysis_id, track_id=item.track_id, suggestion=item.suggestion,
                kit_group=item.kit_group, kit_color=item.kit_color, kit_tracks=item.kit_tracks,
                confidence=round(item.confidence, 3), reason=item.reason.strip()))
        return rows

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
                samples=item.samples,
                exceed_ratio=round(item.exceed_ratio, 4) if item.exceed_ratio is not None else None,
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
