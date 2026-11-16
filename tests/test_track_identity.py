"""Saying who a track is on the video: a shirt number, the referee or someone outside the game."""

from conftest import register
from test_clip_library import analyse, upload
from test_video_analysis import FakeClient, fake_ai, fake_payload  # noqa: F401  (fixtures)


def analysed(client, coach, match):
    return analyse(client, coach, upload(client, coach, match), fake_payload())


def identity(client, who, analysis_id, **body):
    return client.put(f"/api/analyses/{analysis_id}/tracks/1/identity", headers=who["headers"], json=body)


def track(client, who, analysis_id):
    return client.get(f"/api/analyses/{analysis_id}/tracks", headers=who["headers"]).json()[0]


def squad_player(client, coach, team, number, **extra):
    return client.post(f"/api/teams/{team['id']}/players", headers=coach["headers"],
                       json={"first_name": "Daniel", "last_name": "Montoya", "shirt_number": number, **extra}).json()


def ranking(client, who, team):
    return {row["shirt_number"]: row for row in client.get(f"/api/teams/{team['id']}/player-stats", headers=who["headers"]).json()}


def test_typing_a_shirt_number_links_the_squad_player_who_wears_it(client, coach, analyst, team, match, fake_ai):
    player = squad_player(client, coach, team, 10)
    analysis_id = analysed(client, coach, match)
    body = identity(client, analyst, analysis_id, shirt_number=10).json()
    assert (body["player_id"], body["player_name"], body["player_number"]) == (player["id"], "Daniel Montoya", 10)
    listed = track(client, coach, analysis_id)
    assert (listed["player_id"], listed["player_number"], listed["role"]) == (player["id"], 10, "PLAYER")
    assert ranking(client, coach, team)[10]["detections"] == 2      # the whole track counts for him


def test_a_number_nobody_wears_is_kept_only_as_a_number(client, coach, team, match, fake_ai):
    analysis_id = analysed(client, coach, match)
    body = identity(client, coach, analysis_id, shirt_number=23).json()
    assert body["player_id"] is None and body["player_number"] == 23
    assert track(client, coach, analysis_id)["player_number"] == 23
    cleared = identity(client, coach, analysis_id, shirt_number=None).json()
    assert cleared["player_number"] is None and track(client, coach, analysis_id)["player_number"] is None


def test_a_player_who_left_the_team_is_not_matched_by_his_old_number(client, coach, team, match, fake_ai):
    gone = squad_player(client, coach, team, 9)
    client.request("DELETE", f"/api/players/{gone['id']}", headers=coach["headers"], json={"withdrawal_reason": "Cambió de club"})
    active = squad_player(client, coach, team, 9)
    analysis_id = analysed(client, coach, match)
    assert identity(client, coach, analysis_id, shirt_number=9).json()["player_id"] == active["id"]


def test_the_referee_and_people_outside_are_left_out_of_the_ranking(client, coach, team, match, fake_ai):
    squad_player(client, coach, team, 10)
    analysis_id = analysed(client, coach, match)
    identity(client, coach, analysis_id, shirt_number=10)
    referee = identity(client, coach, analysis_id, role="REFEREE").json()
    assert referee["role"] == "REFEREE" and referee["player_id"] is None
    listed = track(client, coach, analysis_id)
    assert (listed["role"], listed["player_id"], listed["player_number"]) == ("REFEREE", None, None)
    assert ranking(client, coach, team)[10]["detections"] == 0
    assert identity(client, coach, analysis_id, role="OTHER").json()["role"] == "OTHER"
    assert track(client, coach, analysis_id)["role"] == "OTHER"


def test_choosing_a_player_again_undoes_the_referee_mark(client, coach, team, match, fake_ai):
    player = squad_player(client, coach, team, 4)
    analysis_id = analysed(client, coach, match)
    identity(client, coach, analysis_id, role="REFEREE")
    client.put(f"/api/analyses/{analysis_id}/tracks/1/player", headers=coach["headers"], json={"player_id": player["id"]})
    assert track(client, coach, analysis_id)["role"] == "PLAYER"
    identity(client, coach, analysis_id, role="OTHER")
    identity(client, coach, analysis_id, shirt_number=4)
    assert track(client, coach, analysis_id)["role"] == "PLAYER"


def test_unknown_tracks_bad_numbers_and_other_teams_are_refused(client, coach, team, match, fake_ai):
    analysis_id = analysed(client, coach, match)
    assert client.put(f"/api/analyses/{analysis_id}/tracks/99/identity", headers=coach["headers"],
                      json={"shirt_number": 5}).status_code == 404
    assert identity(client, coach, analysis_id, shirt_number=100).status_code == 422
    assert identity(client, coach, analysis_id, role="COACH").status_code == 422
    outsider = register(client, "otro@club.com", "COACH")
    client.post("/api/teams", headers=outsider["headers"], json={"name": "Otro club"})
    assert identity(client, outsider, analysis_id, shirt_number=5).status_code in (403, 404)


def test_the_overlay_carries_the_confidence_of_each_box(client, coach, match, fake_ai):
    analysis_id = analysed(client, coach, match)
    frames = client.get(f"/api/analyses/{analysis_id}/overlay", headers=coach["headers"]).json()["frames"]
    assert all(len(box) == 7 and 0 <= box[6] <= 1 for _, boxes in frames for box in boxes)
