"""What the team did well (migration 0017): stored with the analysis and returned with its explanation."""

from test_video_analysis import FakeClient, fake_ai, fake_payload, video  # noqa: F401  (fixtures)


def result_of(client, coach, video, payload):
    FakeClient.response = payload
    started = client.post(f"/api/videos/{video['id']}/analysis", headers=coach["headers"], json={})
    assert started.status_code in (200, 201, 202), started.text
    return client.get(f"/api/analyses/{started.json()['id']}/result", headers=coach["headers"]).json()


def test_strengths_come_with_the_analysis_and_their_explanation(client, coach, analyst, video):
    payload = fake_payload()
    payload["strengths"].append({
        "id": "LINES_TOGETHER:TEAM_A:defensive_midfield_distance", "code": "LINES_TOGETHER",
        "title": "Líneas juntas al defender", "team": "TEAM_A", "evidence": "En el 80 % de 20 cuadros…",
        "confidence": 0.71, "related_indicators": ["team_a.defensive_midfield_distance"],
        "explanation": {"seen": "Mientras el rival tenía el balón…", "meaning": "Defensa y mediocampo defendieron cerca.",
                        "keep": "Mantener esa distancia corta.", "unexpected": "not stored",
                        "example": {"team": "TEAM_A", "players": [{"id": 1, "team": "TEAM_A", "x": 0.2, "y": 0.5}],
                                    "overlay": {"kind": "lines", "lines": [0.1, 0.2, 0.32], "gap": [0.1, 0.2]}}},
    })
    result = result_of(client, coach, video, payload)
    strengths = result["strengths"]
    assert [s["code"] for s in strengths] == ["LINES_TOGETHER", "NOBODY_ISOLATED"]   # most confident first
    lines = strengths[0]
    assert (lines["team"], lines["title"], lines["confidence"]) == ("TEAM_A", "Líneas juntas al defender", 0.71)
    assert lines["indicator"] == "team_a.defensive_midfield_distance"
    assert lines["explanation"]["keep"] == "Mantener esa distancia corta."
    assert lines["explanation"]["example"]["overlay"]["kind"] == "lines"
    assert "unexpected" not in lines["explanation"]
    # The analyst of the team sees them too; problems and strengths do not mix.
    seen_by_analyst = client.get(f"/api/analyses/{result['analysis']['id']}/result", headers=analyst["headers"]).json()
    assert len(seen_by_analyst["strengths"]) == 2
    assert all(r["title"].startswith("Possible") for r in seen_by_analyst["recommendations"])


def test_strengths_do_not_ring_the_bell(client, coach, video):
    result_of(client, coach, video, fake_payload())
    events = {item["event"] for item in client.get("/api/notifications", headers=coach["headers"]).json()}
    assert "ANALYSIS_COMPLETED" in events
    messages = " ".join(item["message"] for item in client.get("/api/notifications", headers=coach["headers"]).json())
    assert "compañero cerca" not in messages


def test_an_ai_service_without_strengths_still_works(client, coach, video):
    payload = fake_payload()
    del payload["strengths"]
    result = result_of(client, coach, video, payload)
    assert result["analysis"]["status"] == "COMPLETED"
    assert result["strengths"] == []
