"""Isolation between teams: nobody outside a team can read, change or even detect its data.

Team A is fully populated (player, match, event, formation, tactical play with versions, video,
analysis, recommendation, report). The coach and the analyst of team B then call EVERY endpoint
that touches team A. Expected answer: 404, the same as for an id that does not exist.
The administrator gets 403 on tactical content. Finally team A's data must be intact.
"""

import pytest
from conftest import register
from test_video_analysis import FakeClient, FakeRealFactory, fake_payload

from services import ai_client

MISSING_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def world(client, monkeypatch):
    monkeypatch.setitem(ai_client._FACTORIES, "REAL_VIDEO_ANALYSIS", FakeRealFactory)
    FakeClient.response = fake_payload()

    coach_a = register(client, "coach.a@club.com", "COACH")
    h = coach_a["headers"]
    team = client.post("/api/teams", headers=h, json={"name": "Atletico Norte"}).json()
    analyst_a = register(client, "analyst.a@club.com", "ANALYST")
    client.post("/api/teams/join", headers=analyst_a["headers"], json={"invitation_code": team["invitation_code"]})

    player = client.post(f"/api/teams/{team['id']}/players", headers=h,
                         json={"first_name": "Juan", "last_name": "Perez", "shirt_number": 9}).json()
    match = client.post(f"/api/teams/{team['id']}/matches", headers=h,
                        json={"opponent": "Nacional", "match_date": "2026-09-01T15:00:00", "is_home": True}).json()
    match2 = client.post(f"/api/teams/{team['id']}/matches", headers=h,
                         json={"opponent": "Medellin", "match_date": "2026-09-08T15:00:00"}).json()
    event = client.post(f"/api/matches/{match['id']}/events", headers=h,
                        json={"minute": 12, "event_type": "SHOT", "zone": "BOX", "source_x": 90, "source_y": 30}).json()
    formation = client.post("/api/formations", headers=h, json={"name": "4-3-3"}).json()
    play = client.post(f"/api/teams/{team['id']}/tactical-plays", headers=h, json={
        "name": "High press", "action_type": "PRESSING", "configuration": {"formation": "4-3-3"}}).json()
    version2 = client.post(f"/api/tactical-plays/{play['id']}/versions", headers=h,
                           json={"configuration": {"lines": {"defense": 48}}}).json()
    video = client.post(f"/api/matches/{match['id']}/videos", headers=h,
                        files={"video": ("clip.mp4", b"fake-bytes", "video/mp4")}).json()
    analysis = client.post(f"/api/videos/{video['id']}/analysis", headers=h, json={}).json()
    recommendation = client.get(f"/api/matches/{match['id']}/recommendations", headers=h).json()[0]
    report = client.post(f"/api/teams/{team['id']}/reports", headers=h,
                         json={"report_type": "MATCH", "match_id": match["id"]}).json()

    coach_b = register(client, "coach.b@club.com", "COACH")
    team_b = client.post("/api/teams", headers=coach_b["headers"], json={"name": "Deportivo Sur"}).json()
    analyst_b = register(client, "analyst.b@club.com", "ANALYST")
    client.post("/api/teams/join", headers=analyst_b["headers"], json={"invitation_code": team_b["invitation_code"]})

    return {
        "headers_a": h, "team": team["id"], "analyst_a": analyst_a["user"]["id"], "player": player["id"],
        "match": match["id"], "match2": match2["id"], "event": event["id"], "formation": formation["id"],
        "play": play["id"], "version": version2["id"], "video": video["id"], "analysis": analysis["id"],
        "recommendation": recommendation["id"], "report": report["id"],
        "outsiders": {"coach_b": coach_b["headers"], "analyst_b": analyst_b["headers"]},
    }


# (method, path, json body) — every endpoint that reads or changes team data.
ENDPOINTS = [
    ("GET", "/api/teams/{team}", None),
    ("PUT", "/api/teams/{team}", {"name": "Hacked"}),
    ("POST", "/api/teams/{team}/invitation-code", None),
    ("GET", "/api/teams/{team}/analysts", None),
    ("DELETE", "/api/teams/{team}/analysts/{analyst_a}", None),
    ("GET", "/api/teams/{team}/players", None),
    ("POST", "/api/teams/{team}/players", {"first_name": "X", "last_name": "Y"}),
    ("GET", "/api/players/{player}", None),
    ("PUT", "/api/players/{player}", {"first_name": "Hacked"}),
    ("DELETE", "/api/players/{player}", {"withdrawal_reason": "Hacked"}),
    ("GET", "/api/players/{player}/history", None),
    ("GET", "/api/players/{player}/appearances", None),
    ("GET", "/api/teams/{team}/matches", None),
    ("POST", "/api/teams/{team}/matches", {"opponent": "X", "match_date": "2026-10-01T15:00:00"}),
    ("GET", "/api/matches/{match}", None),
    ("PUT", "/api/matches/{match}", {"opponent": "Hacked"}),
    ("PUT", "/api/matches/{match}/result", {"home_score": 0, "away_score": 9}),
    ("DELETE", "/api/matches/{match}", None),
    ("GET", "/api/matches/{match}/neighbors", None),
    ("GET", "/api/matches/{match}/events", None),
    ("POST", "/api/matches/{match}/events", {"minute": 1, "event_type": "SHOT"}),
    ("PUT", "/api/matches/{match}/events/{event}", {"minute": 2, "event_type": "SHOT"}),
    ("DELETE", "/api/matches/{match}/events/{event}", None),
    ("GET", "/api/matches/{match}/formations", None),
    ("POST", "/api/matches/{match}/formations", {"formation_id": "{formation}"}),
    ("GET", "/api/matches/{match}/tactical-plays", None),
    ("POST", "/api/matches/{match}/tactical-plays", {"tactical_play_id": "{play}"}),
    ("DELETE", "/api/matches/{match}/tactical-plays/{play}", None),
    ("GET", "/api/teams/{team}/tactical-plays", None),
    ("POST", "/api/teams/{team}/tactical-plays", {"name": "X", "action_type": "PRESSING", "configuration": {}}),
    ("GET", "/api/tactical-plays/{play}", None),
    ("PUT", "/api/tactical-plays/{play}", {"name": "Hacked"}),
    ("GET", "/api/tactical-plays/{play}/matches", None),
    ("DELETE", "/api/tactical-plays/{play}", None),
    ("GET", "/api/tactical-plays/{play}/versions", None),
    ("POST", "/api/tactical-plays/{play}/versions", {"configuration": {"x": 1}}),
    ("POST", "/api/tactical-plays/{play}/versions/{version}/activate", None),
    ("POST", "/api/tactical-plays/{play}/versions/undo", None),
    ("GET", "/api/matches/{match}/videos", None),
    ("GET", "/api/videos/{video}", None),
    ("DELETE", "/api/videos/{video}", None),
    ("POST", "/api/videos/{video}/analysis", {}),
    ("GET", "/api/videos/{video}/analyses", None),
    ("GET", "/api/analyses/{analysis}", None),
    ("POST", "/api/analyses/{analysis}/cancel", None),
    ("GET", "/api/analyses/{analysis}/result", None),
    ("GET", "/api/analyses/{analysis}/indicators", None),
    ("GET", "/api/analyses/{analysis}/detections", None),
    ("GET", "/api/analyses/{analysis}/tracks", None),
    ("PUT", "/api/analyses/{analysis}/tracks/1/player", {"player_id": None}),
    ("GET", "/api/matches/{match}/recommendations", None),
    ("PATCH", "/api/recommendations/{recommendation}", {"action": "dismiss"}),
    ("GET", "/api/teams/{team}/comparisons?match_ids={match}&match_ids={match2}", None),
    ("GET", "/api/teams/{team}/evolution", None),
    ("GET", "/api/teams/{team}/reports", None),
    ("POST", "/api/teams/{team}/reports", {"report_type": "TEAM_EVOLUTION"}),
    ("GET", "/api/reports/{report}", None),
    ("GET", "/api/reports/{report}/export?format=json", None),
]


def _fill(value, ids):
    if isinstance(value, str):
        return value.format(**ids)
    if isinstance(value, dict):
        return {key: _fill(item, ids) for key, item in value.items()}
    return value


def _call(client, method, path, body, headers, ids):
    return client.request(method, _fill(path, ids), headers=headers, json=_fill(body, ids))


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS, ids=[f"{m} {p}" for m, p, _ in ENDPOINTS])
def test_outsiders_get_not_found(client, world, method, path, body):
    for who, headers in world["outsiders"].items():
        response = _call(client, method, path, body, headers, world)
        assert response.status_code == 404, f"{who}: {response.status_code} {response.text}"
        assert response.json()["code"] == "NOT_FOUND"


def test_outsider_answer_equals_missing_resource(client, world):
    """An existing match of another team is indistinguishable from a match that does not exist."""
    headers = world["outsiders"]["coach_b"]
    existing = client.get(f"/api/matches/{world['match']}", headers=headers)
    missing = client.get(f"/api/matches/{MISSING_ID}", headers=headers)
    assert (existing.status_code, existing.json()) == (missing.status_code, missing.json())


def test_admin_gets_forbidden_on_tactical_content(client, world, admin):
    for method, path, body in ENDPOINTS:
        response = _call(client, method, path, body, admin["headers"], world)
        assert response.status_code == 403, f"{method} {path}: {response.status_code}"
        assert response.json()["code"] == "ADMIN_NO_TACTICAL_ACCESS"


def test_outsider_cannot_attach_foreign_player_to_own_analysis(client, world):
    """Team B cannot link team A's player to a track of its own analysis."""
    headers = world["outsiders"]["coach_b"]
    team_b = client.get("/api/teams/mine", headers=headers).json()
    match_b = client.post(f"/api/teams/{team_b['id']}/matches", headers=headers,
                          json={"opponent": "X", "match_date": "2026-10-01T15:00:00"}).json()
    video_b = client.post(f"/api/matches/{match_b['id']}/videos", headers=headers,
                          files={"video": ("b.mp4", b"bytes", "video/mp4")}).json()
    analysis_b = client.post(f"/api/videos/{video_b['id']}/analysis", headers=headers, json={}).json()
    response = client.put(f"/api/analyses/{analysis_b['id']}/tracks/1/player", headers=headers,
                          json={"player_id": world["player"]})
    assert response.status_code == 404


def test_outsider_cannot_use_foreign_match_in_own_report(client, world):
    headers = world["outsiders"]["coach_b"]
    team_b = client.get("/api/teams/mine", headers=headers).json()
    response = client.post(f"/api/teams/{team_b['id']}/reports", headers=headers,
                           json={"report_type": "MATCH", "match_id": world["match"]})
    assert response.status_code == 404


def test_notifications_only_show_own_team(client, world):
    events_b = client.get("/api/notifications", headers=world["outsiders"]["coach_b"]).json()
    assert all(event["team_id"] != world["team"] for event in events_b)
    events_a = client.get("/api/notifications", headers=world["headers_a"]).json()
    assert events_a and all(event["team_id"] == world["team"] for event in events_a)


def test_team_a_data_is_intact_after_attacks(client, world):
    for method, path, body in ENDPOINTS:
        for headers in world["outsiders"].values():
            _call(client, method, path, body, headers, world)
    h = world["headers_a"]
    assert client.get(f"/api/teams/{world['team']}", headers=h).json()["name"] == "Atletico Norte"
    assert client.get(f"/api/matches/{world['match']}", headers=h).json()["opponent"] == "Nacional"
    assert client.get(f"/api/players/{world['player']}", headers=h).json()["status"] == "ACTIVE"
    assert client.get(f"/api/videos/{world['video']}", headers=h).status_code == 200
    assert client.get(f"/api/tactical-plays/{world['play']}", headers=h).status_code == 200
    assert len(client.get(f"/api/teams/{world['team']}/analysts", headers=h).json()) == 1
    assert client.get(f"/api/reports/{world['report']}", headers=h).status_code == 200
