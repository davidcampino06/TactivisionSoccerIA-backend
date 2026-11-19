"""Suggested training exercise for each kind of possible issue (fixed catalogue, not computed by the AI)."""

from datetime import datetime

from schemas import RecommendationOut
from services.reports import MatchReportView, PdfExporter
from services.training_drills import DRILLS, NOTE, TITLE_TO_CODE, drill_for
from test_report_exports import SNAPSHOT

COMPACTNESS = "Posible problema táctico: baja compactación del equipo"


def test_every_issue_title_of_the_ai_has_a_complete_exercise():
    assert len(TITLE_TO_CODE) == 14 and set(TITLE_TO_CODE.values()) == set(DRILLS) and len(DRILLS) == 12
    for code, drill in DRILLS.items():
        assert all(drill[field].strip() for field in ("name", "objective", "organization", "development", "variant")), code
        assert len(drill["keys"]) >= 2, code


def test_the_exercise_is_found_by_the_stored_title():
    drill = drill_for(COMPACTNESS)
    assert drill["code"] == "LOW_TEAM_COMPACTNESS" and drill["name"] == "Partido en dos franjas" and drill["note"] == NOTE
    assert drill_for("  " + COMPACTNESS + " ") == drill
    assert drill_for("Posible problema táctico: líneas separadas") is None


def test_the_api_sends_the_exercise_with_each_possible_issue():
    out = RecommendationOut(id="r1", match_id="m1", title=COMPACTNESS, description="Revisar la compactación.",
                            severity="HIGH", confidence=0.8, evidence="0,15 > 0,136", created_at=datetime(2026, 11, 18),
                            status="GENERATED")
    assert out.drill["name"] == "Partido en dos franjas"
    other = RecommendationOut(**{**out.model_dump(), "title": "Otro problema", "drill": None})
    assert other.drill is None


def test_the_pdf_explains_the_exercise_under_each_issue():
    issue = {**SNAPSHOT["possible_issues"][0], "issue": COMPACTNESS}
    snapshot = {**SNAPSHOT, "possible_issues": [issue],
                "ai_recommendations": [{"issue": COMPACTNESS, "recommendation": "Revisar.", "confidence": 0.8, "status": "GENERATED"}]}
    blocks = MatchReportView(snapshot, PdfExporter()).blocks()
    details = dict(next(block for block in blocks if block["kind"] == "issue")["details"])
    assert details["Ejercicio sugerido"].startswith("Partido en dos franjas.")
    assert "8 contra 8" in details["Organización"] and details["Recomendación"] == "Revisar."
    assert any(block["kind"] == "text" and block["text"] == NOTE for block in blocks)
    assert MatchReportView(snapshot, PdfExporter()).export().startswith(b"%PDF")
