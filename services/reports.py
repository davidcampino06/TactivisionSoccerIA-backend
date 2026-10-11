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
    VideoAnalysis, utc_now,
)
from services import report_labels as labels
from services.match_timeline import latest_completed_analysis, team_evolution, threshold_status
from errors import DomainError


class ReportError(DomainError):
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
            self._snapshot.setdefault("warnings", []).append("Este partido no tiene un análisis de video completado.")
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
            raise ReportError("Report header is required.", "REPORT_HEADER_REQUIRED")
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
            raise ReportError("Only completed analyses can be reported.", "ANALYSIS_NOT_COMPLETED")
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
    """Implementor side of the Bridge: HOW a report is written (JSON, CSV, PDF).

    It only uses the generic interface of a ReportView (snapshot, rows, blocks), so it never
    needs to know whether the report is about a match, an analysis or the team evolution.
    """

    media_type: str
    extension: str

    @abstractmethod
    def render(self, view: "ReportView") -> str | bytes:
        ...


class JsonExporter(ReportExporter):
    media_type = "application/json"
    extension = "json"

    def render(self, view: "ReportView") -> str:
        return json.dumps(view.snapshot, ensure_ascii=False, indent=2)


class CsvExporter(ReportExporter):
    media_type = "text/csv"
    extension = "csv"

    def render(self, view: "ReportView") -> str:
        rows = view.rows()
        buffer = io.StringIO()
        if rows:
            fieldnames = list(dict.fromkeys(key for row in rows for key in row))
            writer = csv.DictWriter(buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return buffer.getvalue()


class PdfExporter(ReportExporter):
    """Printable document built from the view's blocks (fpdf2, core Helvetica font)."""

    media_type = "application/pdf"
    extension = "pdf"

    def render(self, view: "ReportView") -> bytes:
        from services.report_pdf import render_pdf  # imported lazily: only PDF exports need fpdf2
        return render_pdf(view.title(), view.subtitle(), view.blocks())


class ReportView(ABC):
    """Abstraction side of the Bridge: WHAT a report contains."""

    def __init__(self, snapshot: dict, exporter: ReportExporter, meta: dict | None = None) -> None:
        self.snapshot = snapshot
        self.exporter = exporter
        self.meta = meta or {}

    @abstractmethod
    def rows(self) -> list[dict]:
        """Tabular view used by row-based formats such as CSV."""

    @abstractmethod
    def content_blocks(self) -> list[dict]:
        """Report-specific blocks (see `blocks`)."""

    def title(self) -> str:
        return self.snapshot.get("title", "Reporte")

    def subtitle(self) -> str:
        team = self.snapshot.get("team", {}).get("name", "")
        kind = labels.REPORT_TYPE_LABELS.get(self.snapshot.get("report_type", ""), "Reporte")
        version = f" · versión {self.meta['version']}" if self.meta.get("version") else ""
        return f"{kind} · {team}{version}"

    def blocks(self) -> list[dict]:
        """Format-neutral document: heading, facts, notice, issue and table blocks."""
        header = {"kind": "facts", "items": [
            ("Equipo", self.snapshot.get("team", {}).get("name", "-")),
            ("Generado por", self.snapshot.get("generated_by", "-")),
            ("Fecha de generación", labels.local_datetime(self.snapshot.get("generated_at"), naive_is_utc=True)),
        ]}
        notices = [{"kind": "notice", "text": warning} for warning in self.snapshot.get("warnings", [])]
        return [header, *notices, *self.content_blocks()]

    def export(self) -> str | bytes:
        return self.exporter.render(self)


def _match_facts(match: dict) -> dict:
    result = labels.RESULT_LABELS.get(match.get("result") or "", "")
    return {"kind": "facts", "items": [
        ("Rival", match.get("opponent", "-")),
        ("Fecha", labels.local_datetime(match.get("date"), naive_is_utc=False)),
        ("Condición", "Local" if match.get("is_home") else "Visitante"),
        ("Marcador", f"{match['score']} ({result})" if match.get("score") else "Sin marcador"),
    ]}


class MatchReportView(ReportView):
    def rows(self) -> list[dict]:
        # Column names and labels are Spanish: the CSV is opened by the coach in Excel.
        # "valor" stays numeric (to sort or chart it); "valor_legible" is the formatted text.
        rows = []
        for i in self.snapshot.get("tactical_indicators", []):
            name, team = labels.split_indicator(i["name"])
            rows.append({"seccion": "indicador", "nombre": name, "equipo": team, "valor": i["value"],
                         "valor_legible": labels.format_value(i["value"], i["unit"]),
                         "umbral": labels.format_value(i["threshold"], i["unit"], with_unit=False)
                         if i["threshold"] is not None else "", "codigo": i["name"]})
        rows += [{"seccion": "posible_problema", "nombre": p["issue"], "valor": p["confidence"],
                  "valor_legible": f"confianza {labels.percent(p['confidence'])}", "detalle": p["evidence"],
                  "severidad": labels.SEVERITY_LABELS.get(p["severity"], p["severity"]),
                  "estado": labels.STATUS_LABELS.get(p["status"], p["status"])}
                 for p in self.snapshot.get("possible_issues", [])]
        rows += [{"seccion": "recomendacion", "nombre": r["issue"], "valor": r["confidence"],
                  "valor_legible": f"confianza {labels.percent(r['confidence'])}", "detalle": r["recommendation"]}
                 for r in self.snapshot.get("ai_recommendations", [])]
        return rows

    def content_blocks(self) -> list[dict]:
        blocks: list[dict] = []
        if self.snapshot.get("match"):
            blocks += [{"kind": "heading", "text": "Partido"}, _match_facts(self.snapshot["match"])]
        events = self.snapshot.get("events") or []
        if events:
            blocks += [{"kind": "heading", "text": "Eventos del partido"},
                       {"kind": "table", "columns": ["Minuto", "Evento", "Zona", "Resultado"], "widths": [1, 2, 2, 2],
                        "rows": [[f"{e['minute']}'", labels.event_label(e["type"]), labels.event_label(e.get("zone")),
                                  labels.event_label(e.get("result"))] for e in events]}]

        analysis = self.snapshot.get("analysis")
        if analysis:
            simulated = analysis.get("label") == "SIMULATION MODE"
            blocks += [{"kind": "heading", "text": "Análisis de video"}, {"kind": "facts", "items": [
                ("Tipo de análisis", "Modo simulación" if simulated else "Análisis de video real"),
                ("Modelo", "Generador de posiciones sintéticas" if simulated
                 else f"{analysis.get('model') or '-'} {analysis.get('model_version') or ''}".strip()),
                ("Completado", labels.local_datetime(analysis.get("completed_at"), naive_is_utc=True)),
            ]}]
            if simulated:
                blocks.append({"kind": "notice", "text": "MODO SIMULACIÓN: datos sintéticos, no es un análisis de video real."})

        issues = self.snapshot.get("possible_issues") or []
        recommendations = {r["issue"]: r["recommendation"] for r in self.snapshot.get("ai_recommendations", [])}
        if analysis is not None:
            blocks.append({"kind": "heading", "text": "Posibles problemas tácticos"})
            if not issues:
                blocks.append({"kind": "text", "text": "No se detectaron posibles problemas tácticos."})
            for issue in issues:
                blocks.append({
                    "kind": "issue", "title": issue["issue"],
                    "meta": f"Severidad {labels.SEVERITY_LABELS.get(issue['severity'], issue['severity']).lower()} · "
                            f"confianza {labels.percent(issue['confidence'])} · "
                            f"{labels.STATUS_LABELS.get(issue['status'], issue['status']).lower()}",
                    "severity": issue["severity"], "evidence": issue["evidence"],
                    "recommendation": recommendations.get(issue["issue"], ""),
                })

        indicators = self.snapshot.get("tactical_indicators") or []
        if indicators:
            rows = []
            for i in sorted(indicators, key=lambda item: item["name"]):
                name, team = labels.split_indicator(i["name"])
                status = threshold_status(i["name"], i["value"], i["threshold"])
                rows.append([name, team, labels.format_value(i["value"], i["unit"]),
                             labels.format_value(i["threshold"], i["unit"], with_unit=False)
                             if i["threshold"] is not None else "-",
                             {"EXCEEDS": "Supera", "OK": "Dentro"}.get(status or "", "-")])
            blocks += [{"kind": "heading", "text": "Indicadores tácticos"},
                       {"kind": "text", "text": "«Supera» indica que el valor está del lado del umbral que la IA "
                                                "considera un posible riesgo."},
                       {"kind": "table", "columns": ["Indicador", "Equipo", "Valor", "Umbral", "Estado"],
                        "widths": [3.8, 1.5, 3.2, 1.1, 1.1], "rows": rows}]
        return blocks


class AnalysisReportView(MatchReportView):
    pass


class EvolutionReportView(ReportView):
    def rows(self) -> list[dict]:
        evolution = self.snapshot.get("team_evolution", {})
        opponents = [m["opponent"] for m in evolution.get("matches", [])]
        rows = []
        for trend in evolution.get("trends", []):
            name, team = labels.split_indicator(trend["indicator"])
            row = {"indicador": name, "equipo": team,
                   "tendencia": labels.TREND_LABELS.get(trend["trend"], trend["trend"]),
                   "valoracion": labels.ASSESSMENT_LABELS.get(trend.get("assessment") or "", ""),
                   "pendiente": trend["slope"], "codigo": trend["indicator"]}
            row.update({f"{index + 1}_{opponent}": value for index, (opponent, value)
                        in enumerate(zip(opponents, trend["values"]))})
            rows.append(row)
        return rows

    def content_blocks(self) -> list[dict]:
        evolution = self.snapshot.get("team_evolution", {})
        matches = evolution.get("matches", [])
        blocks: list[dict] = [{"kind": "notice", "text": warning} for warning in evolution.get("warnings", [])]
        blocks += [{"kind": "heading", "text": "Partidos analizados"},
                   {"kind": "table", "columns": ["#", "Fecha", "Rival", "Resultado"], "widths": [0.5, 2, 4, 2],
                    "rows": [[str(index + 1), labels.local_datetime(m["match_date"], naive_is_utc=False)[:10], m["opponent"],
                              labels.RESULT_LABELS.get(m.get("result") or "", "-")] for index, m in enumerate(matches)]}]
        trends = evolution.get("trends", [])
        order = {"WORSENING": 0, "IMPROVING": 1, "STABLE": 2}
        rows = []
        for trend in sorted(trends, key=lambda item: (order.get(item.get("assessment") or "", 3), item["indicator"])):
            name, team = labels.split_indicator(trend["indicator"])
            known = [value for value in trend["values"] if value is not None]
            rows.append([name, team,
                         labels.format_value(known[0], trend.get("unit"), with_unit=False) if known else "-",
                         labels.format_value(known[-1], trend.get("unit"), with_unit=False) if known else "-",
                         labels.TREND_LABELS.get(trend["trend"], trend["trend"]),
                         labels.ASSESSMENT_LABELS.get(trend.get("assessment") or "", "-")])
        blocks += [{"kind": "heading", "text": "Tendencia de los indicadores"},
                   {"kind": "text", "text": "Primer y último valor de cada indicador; la valoración indica si se aleja "
                                            "(mejora) o se acerca (empeora) al lado del umbral que es un riesgo."},
                   {"kind": "table", "columns": ["Indicador", "Equipo", "Primero", "Último", "Tendencia", "Valoración"],
                    "widths": [3.6, 1.5, 1.2, 1.2, 1.6, 1.4], "rows": rows}]
        return blocks


VIEWS = {"MATCH": MatchReportView, "VIDEO_ANALYSIS": AnalysisReportView, "TEAM_EVOLUTION": EvolutionReportView}
EXPORTERS = {"json": JsonExporter, "csv": CsvExporter, "pdf": PdfExporter}
FILE_LABELS = {"MATCH": "partido", "VIDEO_ANALYSIS": "analisis", "TEAM_EVOLUTION": "evolucion"}


def export_report(report: Report, export_format: str) -> tuple[str | bytes, str, str]:
    exporter_class = EXPORTERS.get(export_format)
    if exporter_class is None:
        raise ReportError(f"Unsupported format '{export_format}'. Use: {', '.join(EXPORTERS)}", "UNSUPPORTED_EXPORT_FORMAT")
    exporter = exporter_class()
    view = VIEWS[report.report_type](json.loads(report.snapshot_data), exporter, {"version": report.version})
    file_name = f"reporte_{FILE_LABELS.get(report.report_type, 'tactivision')}_v{report.version}.{exporter.extension}"
    return view.export(), exporter.media_type, file_name
