"""The review inbox: everything of our team still waiting for a person, across all matches."""

import pytest
from conftest import register
from test_video_analysis import FakeClient, fake_ai, fake_payload  # noqa: F401  (fixtures)


def analyse(client, headers, team, opponent, date, payload):
    match = client.post(f"/api/teams/{team['id']}/matches", headers=headers,
                        json={"opponent": opponent, "match_date": date}).json()
    video = client.post(f"/api/matches/{match['id']}/videos", headers=headers,
                        files={"video": ("clip.mp4", b"fake-bytes", "video/mp4")}).json()
    FakeClient.response = payload
    analysis = client.post(f"/api/videos/{video['id']}/analysis", headers=headers, json={}).json()
    return match, analysis["id"]


def with_own_team(own_team):
    payload = fake_payload()
    payload.setdefault("teams", {})["own_team"] = own_team
    payload["strengths"][0]["team"] = "TEAM_A"
    return payload


@pytest.fixture
def inbox_url(team):
    return f"/api/teams/{team['id']}/review-inbox"


def test_lists_open_problems_and_unreviewed_strengths_with_their_match(client, coach, team, fake_ai, inbox_url):
    match, analysis_id = analyse(client, coach["headers"], team, "Nacional", "2026-09-01T15:00:00", fake_payload())
    inbox = client.get(inbox_url, headers=coach["headers"]).json()
    [problem] = inbox["problems"]
    [strength] = inbox["strengths"]
    assert problem["severity"] == "HIGH" and problem["notes"] == []
    assert problem["context"]["opponent"] == "Nacional" and problem["context"]["analysis_id"] == analysis_id
    assert strength["status"] == "GENERATED" and strength["context"]["match_id"] == match["id"]
    assert inbox["matches"] == [{"match_id": match["id"], "opponent": "Nacional",
                                 "match_date": "2026-09-01T15:00:00", "problems": 1, "strengths": 1}]


def test_reviewed_items_leave_the_inbox(client, coach, analyst, team, fake_ai, inbox_url):
    _, analysis_id = analyse(client, coach["headers"], team, "Nacional", "2026-09-01T15:00:00", fake_payload())
    inbox = client.get(inbox_url, headers=analyst["headers"]).json()
    problem, strength = inbox["problems"][0], inbox["strengths"][0]
    client.patch(f"/api/recommendations/{problem['id']}", headers=analyst["headers"], json={"action": "review"})
    assert len(client.get(inbox_url, headers=analyst["headers"]).json()["problems"]) == 1  # reviewed is still open
    client.patch(f"/api/recommendations/{problem['id']}", headers=analyst["headers"], json={"action": "confirm"})
    client.patch(f"/api/analyses/{analysis_id}/strengths/{strength['id']}", headers=analyst["headers"],
                 json={"action": "dismiss"})
    assert client.get(inbox_url, headers=analyst["headers"]).json() == {
        "problems": [], "strengths": [], "matches": [], "rival_problems": 0}


def test_only_our_team_items_when_the_analysis_knows_which_team_is_ours(client, coach, team, fake_ai, inbox_url):
    analyse(client, coach["headers"], team, "Nacional", "2026-09-01T15:00:00", with_own_team("TEAM_B"))
    inbox = client.get(inbox_url, headers=coach["headers"]).json()
    assert inbox["problems"] == [] and inbox["strengths"] == []  # both items are of TEAM_A, the rival
    assert inbox["rival_problems"] == 1

    analyse(client, coach["headers"], team, "Medellín", "2026-09-08T15:00:00", with_own_team("TEAM_A"))
    inbox = client.get(inbox_url, headers=coach["headers"]).json()
    assert [p["context"]["opponent"] for p in inbox["problems"]] == ["Medellín"]
    assert [s["context"]["own_team"] for s in inbox["strengths"]] == ["TEAM_A"]


def test_most_urgent_problem_first_and_newest_match_first(client, coach, team, fake_ai, inbox_url):
    low = fake_payload()
    low["recommendations"][0]["severity"] = "LOW"
    analyse(client, coach["headers"], team, "Nacional", "2026-09-08T15:00:00", low)
    analyse(client, coach["headers"], team, "Medellín", "2026-09-01T15:00:00", fake_payload())
    inbox = client.get(inbox_url, headers=coach["headers"]).json()
    assert [(p["severity"], p["context"]["opponent"]) for p in inbox["problems"]] == [("HIGH", "Medellín"), ("LOW", "Nacional")]
    assert [m["opponent"] for m in inbox["matches"]] == ["Nacional", "Medellín"]


def test_the_inbox_is_private(client, coach, team, fake_ai, inbox_url):
    analyse(client, coach["headers"], team, "Nacional", "2026-09-01T15:00:00", fake_payload())
    outsider = register(client, "otro@club.com", "COACH")
    client.post("/api/teams", headers=outsider["headers"], json={"name": "Otro club"})
    assert client.get(inbox_url, headers=outsider["headers"]).status_code in (403, 404)
