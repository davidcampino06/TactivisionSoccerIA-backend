"""Player participation (data of the ranking built with a binary search tree in the app)."""

from conftest import register
from test_video_analysis import FakeClient, FakeRealFactory, fake_payload

from services import ai_client


def test_participation_counts_only_linked_tracks(client, coach, team, monkeypatch):
    monkeypatch.setitem(ai_client._FACTORIES, "REAL_VIDEO_ANALYSIS", FakeRealFactory)
    FakeClient.response = fake_payload()
    h = coach["headers"]
    nine = client.post(f"/api/teams/{team['id']}/players", headers=h,
                       json={"first_name": "Juan", "last_name": "Perez", "shirt_number": 9}).json()
    two = client.post(f"/api/teams/{team['id']}/players", headers=h,
                      json={"first_name": "Luis", "last_name": "Gomez", "shirt_number": 2}).json()
    gone = client.post(f"/api/teams/{team['id']}/players", headers=h,
                       json={"first_name": "Old", "last_name": "Player", "shirt_number": 30}).json()
    client.request("DELETE", f"/api/players/{gone['id']}", headers=h, json={"withdrawal_reason": "Transferred"})

    stats = client.get(f"/api/teams/{team['id']}/player-stats", headers=h).json()
    assert [row["shirt_number"] for row in stats] == [2, 9]  # roster order, no inactive players
    assert all(row["detections"] == 0 and row["seconds"] == 0 for row in stats)

    match = client.post(f"/api/teams/{team['id']}/matches", headers=h,
                        json={"opponent": "Nacional", "match_date": "2026-09-01T15:00:00"}).json()
    video = client.post(f"/api/matches/{match['id']}/videos", headers=h,
                        files={"video": ("clip.mp4", b"fake-bytes", "video/mp4")}).json()
    analysis = client.post(f"/api/videos/{video['id']}/analysis", headers=h, json={}).json()
    client.put(f"/api/analyses/{analysis['id']}/tracks/1/player", headers=h, json={"player_id": nine["id"]})

    by_number = {row["shirt_number"]: row for row in client.get(f"/api/teams/{team['id']}/player-stats", headers=h).json()}
    assert (by_number[9]["matches"], by_number[9]["detections"], by_number[9]["seconds"]) == (1, 2, 0.12)
    assert by_number[2]["detections"] == 0 and two["id"] == by_number[2]["player_id"]


def test_participation_is_private(client, team):
    outsider = register(client, "coach.b@club.com", "COACH")["headers"]
    assert client.get(f"/api/teams/{team['id']}/player-stats", headers=outsider).status_code == 404
