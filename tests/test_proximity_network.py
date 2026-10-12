"""The proximity network (graph + BFS from the AI Service) is validated, stored and returned."""

import pytest
from test_video_analysis import FakeClient, FakeRealFactory, fake_payload

from services import ai_client
from services.ai_client import AIResponseError, AIResponseValidator


def network():
    return {
        "frame_number": 3, "timestamp_seconds": 0.12, "link_distance": 0.2,
        "teams": {"TEAM_A": {
            "nodes": [{"track_id": 1, "x": 0.1, "y": 0.4, "degree": 1, "group": 0},
                      {"track_id": 2, "x": 0.2, "y": 0.4, "degree": 1, "group": 0},
                      {"track_id": 3, "x": 0.9, "y": 0.4, "degree": 0, "group": 1}],
            "links": [[1, 2]], "groups": 2, "isolated": [3], "diameter": 1,
            "hops": {"1": {"1": 0, "2": 1}, "2": {"2": 0, "1": 1}, "3": {"3": 0}},
        }},
    }


@pytest.fixture
def analysed(client, coach, team, monkeypatch):
    def run(payload):
        monkeypatch.setitem(ai_client._FACTORIES, "REAL_VIDEO_ANALYSIS", FakeRealFactory)
        FakeClient.response = payload
        h = coach["headers"]
        match = client.post(f"/api/teams/{team['id']}/matches", headers=h,
                            json={"opponent": "Nacional", "match_date": "2026-09-01T15:00:00"}).json()
        video = client.post(f"/api/matches/{match['id']}/videos", headers=h,
                            files={"video": ("clip.mp4", b"fake-bytes", "video/mp4")}).json()
        analysis = client.post(f"/api/videos/{video['id']}/analysis", headers=h, json={}).json()
        return client.get(f"/api/analyses/{analysis['id']}/result", headers=h).json()
    return run


def test_network_is_stored_and_returned(analysed):
    result = analysed({**fake_payload(), "proximity_network": network()})
    stored = result["proximity_network"]
    assert stored["link_distance"] == 0.2
    team_a = stored["teams"]["TEAM_A"]
    assert team_a["groups"] == 2 and team_a["isolated"] == [3]
    assert team_a["links"] == [[1, 2]] and team_a["hops"]["1"]["2"] == 1


def test_analyses_without_network_still_work(analysed):
    result = analysed(fake_payload())
    assert result["analysis"]["status"] == "COMPLETED"
    assert result["proximity_network"] is None


def test_invalid_network_is_rejected():
    broken = network()
    broken["teams"]["TEAM_A"]["nodes"][0]["x"] = 7  # outside the image
    with pytest.raises(AIResponseError):
        AIResponseValidator("REAL_VIDEO_ANALYSIS").validate({**fake_payload(), "proximity_network": broken})
    unknown_team = network()
    unknown_team["teams"] = {"TEAM_C": unknown_team["teams"]["TEAM_A"]}
    with pytest.raises(AIResponseError):
        AIResponseValidator("REAL_VIDEO_ANALYSIS").validate({**fake_payload(), "proximity_network": unknown_team})
