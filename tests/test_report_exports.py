"""Report exports: Spanish labels and the format-neutral blocks behind the PDF (Bridge)."""

from services import report_labels as labels
from services.reports import CsvExporter, JsonExporter, MatchReportView, PdfExporter

SNAPSHOT = {
    "report_type": "MATCH", "title": "Reporte del partido vs Rival", "team": {"name": "Atlético Norte"},
    "generated_by": "Mateo Ríos", "generated_at": "2026-10-11T00:47:00",
    "match": {"opponent": "Rival", "date": "2026-10-10T20:00:00", "is_home": True, "score": "2-1", "result": "WIN"},
    "events": [{"minute": 12, "second": 0, "type": "SHOT", "zone": "BOX", "result": "GOAL"}],
    "analysis": {"label": "REAL VIDEO ANALYSIS", "model": "YOLO26n", "model_version": "8.4", "completed_at": None},
    "possible_issues": [{"issue": "Posible problema táctico: líneas separadas", "evidence": "0,3 > 0,22",
                         "confidence": 0.81, "severity": "HIGH", "status": "CONFIRMED", "related_indicators": []}],
    "ai_recommendations": [{"issue": "Posible problema táctico: líneas separadas", "recommendation": "Juntar líneas.",
                            "confidence": 0.81, "status": "CONFIRMED"}],
    "tactical_indicators": [{"name": "team_a.defensive_midfield_distance", "value": 0.3, "unit": "frame_width_ratio",
                             "threshold": 0.22}],
}


def test_labels_are_spanish():
    assert labels.split_indicator("team_b.team_width") == ("Ancho del equipo", "Equipo B")
    assert labels.split_indicator("match.ball_position_x") == ("Posición del balón (horizontal)", "Partido")
    assert labels.format_value(0.42, "frame_width_ratio") == "42 % del ancho de imagen"
    assert labels.format_value(6.777, "players") == "6,78 jugadores"
    assert labels.event_label("shot") == "Remate" and labels.event_label("Jugada libre") == "Jugada libre"
    assert labels.local_datetime("2026-10-11T00:47:00", naive_is_utc=True) == "10/10/2026 19:47"  # UTC -> Colombia
    assert labels.local_datetime("2026-10-10T20:00:00", naive_is_utc=False) == "10/10/2026 20:00"


def test_same_view_three_formats():
    """Bridge: one report view, three exporters that never look at the report type."""
    json_text = MatchReportView(SNAPSHOT, JsonExporter()).export()
    csv_text = MatchReportView(SNAPSHOT, CsvExporter()).export()
    pdf_bytes = MatchReportView(SNAPSHOT, PdfExporter(), {"version": 3}).export()
    assert '"opponent": "Rival"' in json_text
    assert "Distancia defensa-mediocampo" in csv_text and "30 % del ancho de imagen" in csv_text
    assert pdf_bytes.startswith(b"%PDF") and len(pdf_bytes) > 1500


def test_blocks_describe_the_document():
    view = MatchReportView(SNAPSHOT, PdfExporter(), {"version": 3})
    kinds = [block["kind"] for block in view.blocks()]
    assert kinds[0] == "facts" and "issue" in kinds and kinds.count("table") == 2
    indicators = [block for block in view.blocks() if block["kind"] == "table"][-1]
    assert indicators["rows"][0][-1] == "Supera"  # 0.30 is above the 0.22 threshold
    assert view.subtitle() == "Reporte de partido · Atlético Norte · versión 3"


def test_report_list_shows_author_and_only_coach_deletes(client, coach, team, match, analyst):
    created = client.post(f"/api/teams/{team['id']}/reports", headers=analyst["headers"],
                          json={"report_type": "MATCH", "match_id": match["id"]})
    assert created.status_code == 201 and created.json()["generated_by_name"] == "Test Analyst"
    listed = client.get(f"/api/teams/{team['id']}/reports", headers=coach["headers"]).json()
    assert listed[0]["generated_by_name"] == "Test Analyst"

    report_id = created.json()["id"]
    denied = client.delete(f"/api/reports/{report_id}", headers=analyst["headers"])
    assert denied.status_code == 403 and denied.json()["code"] == "ROLE_NOT_ALLOWED"
    assert client.delete(f"/api/reports/{report_id}", headers=coach["headers"]).status_code == 204
    assert client.get(f"/api/reports/{report_id}", headers=coach["headers"]).status_code == 404
