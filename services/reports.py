"""Reports: Builder + Bridge.

Builder: a report snapshot is assembled step by step (header, match, events, analysis,
indicators, possible issues, recommendations, evolution). ``ReportDirector`` knows which
steps each report type needs, so the three report types reuse the same builder.

Bridge: "what is exported" (the report abstraction: MatchReportView, AnalysisReportView,
EvolutionReportView) is separated from "how it is exported" (the implementor: JsonExporter,
CsvExporter). New formats (PDF) or new report types grow independently: N + M classes
instead of N x M.
"""

from __future__ import annotations

import csv
import io
import json
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    AIRecommendation, Match, MatchEvent, RecommendationIndicator, Report, TacticalIndicator, Team, User,
    Video, VideoAnalysis, utc_now,
)
from services.match_timeline import latest_completed_analysis, team_evolution


class ReportError(ValueError):
    pass


# ---------------------------------------------------------------------- builder
class ReportBuilder:
    def __init__(self) -> None:
        self._snapshot: dict[str, Any] = {"sections": []}

    def header(self, report_type: str, title: str, team: Team, author: User) -> "ReportBuilder":
        self._snapshot.update({
            "report_type": report_type, "title": title,
            "team": {"id": team.id, "name": team.name, "category": team.category},
            "generated_by": f"{author.first_name} {author.last_name}",
            "generated_at": utc_now().isoformat(),
        })
        return self

    def match(self, match: Match) -> "ReportBuilder":
        self._snapshot["match"] = {
            "id": match.id, "opponent": match.opponent, "date": match.match_date.isoformat(),
            "is_home": match.is_home, "score": f"{match.home_score}-{match.away_score}"
            if match.home_score is not None else None, "result": match.result, "status": match.status,
        }
        self._snapshot["sections"].append("match")
        return self

    def events(self, events: list[MatchEvent]) -> "ReportBuilder":
        self._snapshot["events"] = [
            {"minute": e.minute, "second": e.second, "type": e.event_type, "zone": e.zone, "result": e.result}
            for e in sorted(events, key=lambda e: (e.minute, e.second))
        ]
        self._snapshot["sections"].append("events")
        return self

    def analysis(self, analysis: VideoAnalysis | None) -> "ReportBuilder":
        if analysis is None:
            self._snapshot["analysis"] = None
            self._snapshot.setdefault("warnings", []).append("No completed video analysis for this match.")
        else:
            self._snapshot["analysis"] = {
                "id": analysis.id, "label": "SIMULATION MODE" if analysis.analysis_mode == "SIMULATION_MODE"
                else "REAL VIDEO ANALYSIS", "model": analysis.model_name, "model_version": analysis.model_version,
                "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None,
                "warnings": analysis.warning_message,
            }
        self._snapshot["sections"].append("analysis")
        return self

    def indicators(self, indicators: list[TacticalIndicator]) -> "ReportBuilder":
        self._snapshot["tactical_indicators"] = [
            {"name": i.name, "value": i.value, "unit": i.unit, "threshold": i.threshold} for i in indicators
        ]
        self._snapshot["sections"].append("tactical_indicators")
        return self

    def recommendations(self, recommendations: list[tuple[AIRecommendation, list[str]]]) -> "ReportBuilder":
        self._snapshot["possible_issues"] = [
            {"issue": r.title, "evidence": r.evidence, "confidence": r.confidence, "severity": r.severity,
             "status": r.status, "related_indicators": names}
            for r, names in recommendations if r.status != "DISMISSED"
        ]
        self._snapshot["ai_recommendations"] = [
            {"recommendation": r.description, "issue": r.title, "confidence": r.confidence, "status": r.status}
            for r, _ in recommendations if r.status != "DISMISSED"
        ]
        self._snapshot["sections"] += ["possible_issues", "ai_recommendations"]
        return self

    def evolution(self, evolution: dict) -> "ReportBuilder":
        self._snapshot["team_evolution"] = evolution
        self._snapshot["sections"].append("team_evolution")
        return self

    def build(self) -> dict[str, Any]:
        if "report_type" not in self._snapshot:
            raise ReportError("Report header is required.")
        return self._snapshot


def _recommendations_with_indicators(db: Session, analysis_id: str) -> list[tuple[AIRecommendation, list[str]]]:
    rows = (db.query(AIRecommendation, TacticalIndicator.name)
              .join(RecommendationIndicator, RecommendationIndicator.recommendation_id == AIRecommendation.id)
              .join(TacticalIndicator, TacticalIndicator.id == RecommendationIndicator.indicator_id)
              .filter(TacticalIndicator.video_analysis_id == analysis_id).all())
    grouped: dict[str, tuple[AIRecommendation, list[str]]] = {}
    for recommendation, name in rows:
        grouped.setdefault(recommendation.id, (recommendation, []))[1].append(name)
    return sorted(grouped.values(), key=lambda item: item[0].confidence, reverse=True)


class ReportDirector:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _analysis_sections(self, builder: ReportBuilder, analysis: VideoAnalysis | None) -> None:
        builder.analysis(analysis)
        if analysis:
            builder.indicators(self._db.query(TacticalIndicator)
                               .filter(TacticalIndicator.video_analysis_id == analysis.id).all())
            builder.recommendations(_recommendations_with_indicators(self._db, analysis.id))

    def match_report(self, team: Team, author: User, title: str, match: Match) -> dict:
        builder = ReportBuilder().header("MATCH", title, team, author).match(match)
        builder.events(self._db.query(MatchEvent).filter(MatchEvent.match_id == match.id).all())
        self._analysis_sections(builder, latest_completed_analysis(self._db, match.id))
        return builder.build()

    def analysis_report(self, team: Team, author: User, title: str, analysis: VideoAnalysis) -> dict:
        if analysis.status != "COMPLETED":
            raise ReportError("Only completed analyses can be reported.")
        match = self._db.get(Match, analysis.video.match_id)
        builder = ReportBuilder().header("VIDEO_ANALYSIS", title, team, author).match(match)
        self._analysis_sections(builder, analysis)
        return builder.build()

    def evolution_report(self, team: Team, author: User, title: str, match_ids: list[str] | None) -> dict:
        evolution = team_evolution(self._db, team.id, match_ids)
        return ReportBuilder().header("TEAM_EVOLUTION", title, team, author).evolution(evolution).build()


def save_report(db: Session, team: Team, author: User, report_type: str, title: str, snapshot: dict) -> Report:
    last_version = (db.query(func.max(Report.version))
                      .filter(Report.team_id == team.id, Report.report_type == report_type, Report.title == title)
                      .scalar()) or 0
    report = Report(team_id=team.id, generated_by=author.id, title=title, report_type=report_type,
                    version=last_version + 1, snapshot_data=json.dumps(snapshot, ensure_ascii=False))
    db.add(report)
    return report


# ----------------------------------------------------------------------- bridge
class ReportExporter(ABC):
    """Implementor side of the Bridge."""

    media_type: str
    extension: str

    @abstractmethod
    def render(self, document: dict, rows: list[dict]) -> str:
        ...


class JsonExporter(ReportExporter):
    media_type = "application/json"
    extension = "json"

    def render(self, document: dict, rows: list[dict]) -> str:
        return json.dumps(document, ensure_ascii=False, indent=2)


class CsvExporter(ReportExporter):
    media_type = "text/csv"
    extension = "csv"

    def render(self, document: dict, rows: list[dict]) -> str:
        buffer = io.StringIO()
        if rows:
            fieldnames = list(dict.fromkeys(key for row in rows for key in row))
            writer = csv.DictWriter(buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return buffer.getvalue()


class ReportView(ABC):
    """Abstraction side of the Bridge."""

    def __init__(self, snapshot: dict, exporter: ReportExporter) -> None:
        self.snapshot = snapshot
        self.exporter = exporter

    @abstractmethod
    def rows(self) -> list[dict]:
        """Tabular view used by row-based formats such as CSV."""

    def export(self) -> str:
        return self.exporter.render(self.snapshot, self.rows())


class MatchReportView(ReportView):
    def rows(self) -> list[dict]:
        rows = [{"section": "indicator", "name": i["name"], "value": i["value"], "unit": i["unit"],
                 "threshold": i["threshold"]} for i in self.snapshot.get("tactical_indicators", [])]
        rows += [{"section": "possible_issue", "name": p["issue"], "value": p["confidence"], "unit": "confidence",
                  "detail": p["evidence"], "severity": p["severity"]} for p in self.snapshot.get("possible_issues", [])]
        rows += [{"section": "recommendation", "name": r["issue"], "value": r["confidence"], "unit": "confidence",
                  "detail": r["recommendation"]} for r in self.snapshot.get("ai_recommendations", [])]
        return rows


class AnalysisReportView(MatchReportView):
    pass


class EvolutionReportView(ReportView):
    def rows(self) -> list[dict]:
        evolution = self.snapshot.get("team_evolution", {})
        opponents = [m["opponent"] for m in evolution.get("matches", [])]
        rows = []
        for trend in evolution.get("trends", []):
            row = {"indicator": trend["indicator"], "trend": trend["trend"], "slope": trend["slope"]}
            row.update({f"{index + 1}_{opponent}": value for index, (opponent, value)
                        in enumerate(zip(opponents, trend["values"]))})
            rows.append(row)
        return rows


VIEWS = {"MATCH": MatchReportView, "VIDEO_ANALYSIS": AnalysisReportView, "TEAM_EVOLUTION": EvolutionReportView}
EXPORTERS = {"json": JsonExporter, "csv": CsvExporter}


def export_report(report: Report, export_format: str) -> tuple[str, str, str]:
    exporter_class = EXPORTERS.get(export_format)
    if exporter_class is None:
        raise ReportError(f"Unsupported format '{export_format}'. Use: {', '.join(EXPORTERS)}")
    exporter = exporter_class()
    view = VIEWS[report.report_type](json.loads(report.snapshot_data), exporter)
    file_name = f"report_{report.report_type.lower()}_v{report.version}.{exporter.extension}"
    return view.export(), exporter.media_type, file_name
