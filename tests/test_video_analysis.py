"""Video analysis flow with a fake AI source (registered through the Abstract Factory hook).
The real Backend <-> AI Service integration is verified in tests/e2e_check.py."""

import pytest

from services import ai_client
from services.ai_client import AIServiceError, AnalysisSourceFactory, AIAnalysisClient


def fake_payload(mode="REAL_VIDEO_ANALYSIS"):
    return {
        "status": "COMPLETED", "mode": mode, "model": "YOLO26n", "model_version": "ultralytics-8.4.38",
        "video": {"duration_seconds": 12.4}, "frames_processed": 2, "players_detected": 2, "ball_detected": True,
        "detections": [
            {"frame_number": 0, "timestamp": 0.0, "object_type": "PLAYER", "confidence": 0.9, "bounding_box_x": 10,
             "bounding_box_y": 20, "bounding_box_width": 30, "bounding_box_height": 60, "track_id": 1},
            {"frame_number": 3, "timestamp": 0.12, "object_type": "PLAYER", "confidence": 0.88, "bounding_box_x": 12,
             "bounding_box_y": 20, "bounding_box_width": 30, "bounding_box_height": 60, "track_id": 1},
            {"frame_number": 3, "timestamp": 0.12, "object_type": "BALL", "confidence": 0.4, "bounding_box_x": 50,
             "bounding_box_y": 50, "bounding_box_width": 5, "bounding_box_height": 5, "track_id": None},
        ],
        "tracking": [{"track_id": 1}],
        "tactical_indicators": [
            {"name": "team_a.defensive_midfield_distance", "value": 0.31, "unit": "frame_width_ratio", "threshold": 0.22},
            {"name": "team_a.team_width", "value": 0.44, "unit": "frame_height_ratio", "threshold": 0.3},
        ],
        "possible_issues": [{"id": "x"}],
        "recommendations": [{
            "issue_id": "x", "title": "Possible tactical issue: excessive distance between defensive and midfield lines",
            "recommendation": "Review the distance between defensive and midfield lines.", "evidence": "0.31 > 0.22",
            "confidence": 0.71, "severity": "HIGH", "related_indicators": ["team_a.defensive_midfield_distance"]}],
        "warnings": ["Attack direction provided."],
    }


class FakeClient(AIAnalysisClient):
    response: dict | Exception = None
    received_options: dict = {}

    def analyze(self, video_path, options):
        FakeClient.received_options = options
        if isinstance(FakeClient.response, Exception):
            raise FakeClient.response
        return FakeClient.response


class FakeRealFactory(AnalysisSourceFactory):
    mode = "REAL_VIDEO_ANALYSIS"

    def create_client(self):
        return FakeClient()


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch):
    monkeypatch.setitem(ai_client._FACTORIES, "REAL_VIDEO_ANALYSIS", FakeRealFactory)
    FakeClient.response = fake_payload()
    yield


@pytest.fixture
def video(client, coach, match):
    response = client.post(f"/api/matches/{match['id']}/videos", headers=coach["headers"],
                           files={"video": ("clip.mp4", b"fake-bytes-for-storage", "video/mp4")})
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_rejects_wrong_format(client, coach, match):
    response = client.post(f"/api/matches/{match['id']}/videos", headers=coach["headers"],
                           files={"video": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 400


def test_full_analysis_is_persisted(client, coach, team, match, video, analyst):
    headers = analyst["headers"]  # analysts can start analyses for their team
    started = client.post(f"/api/videos/{video['id']}/analysis", headers=headers,
                          json={"frame_stride": 2, "team_a_attack_direction": "left_to_right"})
    assert started.status_code == 202, started.text
    assert FakeClient.received_options["team_a_attack_direction"] == "left_to_right"

    analysis_id = started.json()["id"]
    result = client.get(f"/api/analyses/{analysis_id}/result", headers=headers).json()
    assert result["analysis"]["status"] == "COMPLETED"
    assert result["label"] == "REAL VIDEO ANALYSIS"
    assert result["analysis"]["model_name"] == "YOLO26n"
    assert result["summary"] == {"player_detections": 2, "ball_detections": 1, "frames_with_detections": 2,
                                 "player_tracks": 1, "ball_detected": True}
    assert len(result["indicators"]) == 2
    recommendation = result["recommendations"][0]
    assert recommendation["indicator_names"] == ["team_a.defensive_midfield_distance"]
    assert client.get(f"/api/videos/{video['id']}", headers=headers).json()["duration_seconds"] == 12

    events = [n["event"] for n in client.get("/api/notifications", headers=coach["headers"]).json()]
    assert {"ANALYSIS_QUEUED", "ANALYSIS_STARTED", "ANALYSIS_COMPLETED", "TACTICAL_ALERT"} <= set(events)

    # Correct player identification (human, no biometrics)
    player = client.post(f"/api/teams/{team['id']}/players", headers=coach["headers"],
                         json={"first_name": "Juan", "last_name": "Perez", "shirt_number": 7}).json()
    assigned = client.put(f"/api/analyses/{analysis_id}/tracks/1/player", headers=headers, json={"player_id": player["id"]})
    assert assigned.json()["detections_updated"] == 2
    tracks = client.get(f"/api/analyses/{analysis_id}/tracks", headers=headers).json()
    assert tracks[0]["player_id"] == player["id"]
    detections = client.get(f"/api/analyses/{analysis_id}/detections?track_id=1", headers=headers).json()
    assert all(d["player_number"] == 7 for d in detections)

    # Recommendation review workflow
    rec_url = f"/api/recommendations/{recommendation['id']}"
    assert client.patch(rec_url, headers=headers, json={"action": "review"}).json()["status"] == "REVIEWED"
    assert client.patch(rec_url, headers=headers, json={"action": "confirm"}).json()["status"] == "CONFIRMED"
    assert client.patch(rec_url, headers=headers, json={"action": "dismiss"}).status_code == 409

    # Terminal state cannot be cancelled
    assert client.post(f"/api/analyses/{analysis_id}/cancel", headers=headers).status_code == 409


def test_ai_service_failure_marks_analysis_failed(client, coach, video):
    FakeClient.response = AIServiceError("AI Service unreachable: connection refused")
    analysis = client.post(f"/api/videos/{video['id']}/analysis", headers=coach["headers"], json={}).json()
    body = client.get(f"/api/analyses/{analysis['id']}", headers=coach["headers"]).json()
    assert body["status"] == "FAILED" and "unreachable" in body["warning_message"]
    assert client.get(f"/api/videos/{video['id']}", headers=coach["headers"]).json()["status"] == "UPLOADED"


def test_mode_mismatch_is_rejected(client, coach, video):
    FakeClient.response = fake_payload(mode="SIMULATION_MODE")
    analysis = client.post(f"/api/videos/{video['id']}/analysis", headers=coach["headers"], json={}).json()
    body = client.get(f"/api/analyses/{analysis['id']}", headers=coach["headers"]).json()
    assert body["status"] == "FAILED" and "Expected REAL_VIDEO_ANALYSIS" in body["warning_message"]


def test_reports_comparison_and_evolution(client, coach, team, match, video):
    headers = coach["headers"]
    client.post(f"/api/videos/{video['id']}/analysis", headers=headers, json={})
    report = client.post(f"/api/teams/{team['id']}/reports", headers=headers,
                         json={"report_type": "MATCH", "match_id": match["id"]})
    assert report.status_code == 201, report.text
    snapshot = report.json()["snapshot"]
    assert snapshot["analysis"]["label"] == "REAL VIDEO ANALYSIS"
    assert snapshot["possible_issues"][0]["related_indicators"] == ["team_a.defensive_midfield_distance"]
    again = client.post(f"/api/teams/{team['id']}/reports", headers=headers,
                        json={"report_type": "MATCH", "match_id": match["id"]}).json()
    assert again["version"] == 2

    csv_export = client.get(f"/api/reports/{again['id']}/export?format=csv", headers=headers)
    assert csv_export.headers["content-type"].startswith("text/csv") and "team_a.team_width" in csv_export.text
    assert client.get(f"/api/reports/{again['id']}/export?format=pdf", headers=headers).status_code == 400

    other_ids = []
    for day in ("2026-09-08", "2026-09-15"):
        other = client.post(f"/api/teams/{team['id']}/matches", headers=headers,
                            json={"opponent": f"Rival {day}", "match_date": f"{day}T15:00:00"}).json()
        other_ids.append(other["id"])
    comparison = client.get(f"/api/teams/{team['id']}/comparisons?match_ids={match['id']}&match_ids={other_ids[0]}",
                            headers=headers).json()
    assert comparison["indicators"][0]["values"][0] is not None
    assert any("without a completed analysis" in w for w in comparison["warnings"])
    assert client.get(f"/api/teams/{team['id']}/comparisons?match_ids={match['id']}", headers=headers).status_code == 400

    evolution = client.get(f"/api/teams/{team['id']}/evolution", headers=headers).json()
    assert [m["match_id"] for m in evolution["matches"]][0] == match["id"]
    evolution_report = client.post(f"/api/teams/{team['id']}/reports", headers=headers,
                                   json={"report_type": "TEAM_EVOLUTION"})
    assert evolution_report.status_code == 201
