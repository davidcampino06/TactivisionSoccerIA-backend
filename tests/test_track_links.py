"""Tracks of one player cut in two, and kits of no team: the AI suggests, a person decides."""

from conftest import register
from test_clip_library import analyse, upload
from test_track_identity import ranking, squad_player
from test_video_analysis import FakeClient, fake_ai, fake_payload  # noqa: F401  (fixtures)


def detection(track_id, frame):
    return {"frame_number": frame, "timestamp": frame / 25, "object_type": "PLAYER", "confidence": 0.8,
            "bounding_box_x": 10 + frame, "bounding_box_y": 20, "bounding_box_width": 30, "bounding_box_height": 60,
            "track_id": track_id}


def link(a, b, last, first, **extra):
    return {"from_track": a, "to_track": b, "from_last_frame": last, "to_first_frame": first, "gap_seconds": 0.36,
            "distance_heights": 0.12, "color_distance": 4.28, "same_team": True, "confidence": 0.9, **extra}


def kit(track_id, group=1, color="#3bb3c2", tracks=2):
    return {"track_id": track_id, "suggestion": "GOALKEEPER_OR_REFEREE", "kit_group": group, "kit_color": color,
            "kit_tracks": tracks, "confidence": 0.5,
            "reason": f"Camiseta {color}, que no es de ningún equipo: puede ser un arquero o el árbitro."}


def payload(links=(), kits=()):
    """Player 12 is cut in 12 -> 31 -> 40; the referee is 7 and 8; 5 is somebody else."""
    data = fake_payload()
    data["detections"] = [detection(t, f) for t, frames in
                          {12: (0, 3, 6), 31: (15, 18), 40: (30, 33), 7: (0, 3), 8: (21, 24), 5: (0, 33)}.items()
                          for f in frames]
    data["track_links"] = {"links": list(links), "groups": []}
    data["track_role_suggestions"] = list(kits)
    return data


def analysed(client, coach, match, **parts):
    return analyse(client, coach, upload(client, coach, match), payload(**parts))


def hints(client, who, analysis_id):
    response = client.get(f"/api/analyses/{analysis_id}/identification-hints", headers=who["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def decide(client, who, analysis_id, from_track, decision):
    return client.put(f"/api/analyses/{analysis_id}/track-links/{from_track}", headers=who["headers"],
                      json={"decision": decision})


def identity(client, who, analysis_id, track_id, **body):
    return client.put(f"/api/analyses/{analysis_id}/tracks/{track_id}/identity", headers=who["headers"], json=body)


def numbers(client, who, analysis_id):
    return {t["track_id"]: (t["role"], t["player_number"])
            for t in client.get(f"/api/analyses/{analysis_id}/tracks", headers=who["headers"]).json()}


CHAIN = (link(12, 31, 6, 15), link(31, 40, 18, 30, confidence=0.7))
REFEREE_KIT = (kit(7), kit(8))


def test_the_suggestions_of_the_ai_are_saved_with_the_analysis(client, coach, match, fake_ai):
    analysis_id = analysed(client, coach, match, links=CHAIN, kits=REFEREE_KIT)
    body = hints(client, coach, analysis_id)
    assert [(item["from_track"], item["to_track"], item["status"]) for item in body["links"]] == \
        [(12, 31, "SUGGESTED"), (31, 40, "SUGGESTED")]
    assert body["links"][0]["gap_seconds"] == 0.36 and body["links"][0]["same_team"] is True
    (referee,) = body["kits"]
    assert (referee["tracks"], referee["kit_color"], referee["dismissed"]) == ([7, 8], "#3bb3c2", False)
    assert body["same_player"] == {}


def test_bad_suggestions_are_skipped_and_never_fail_the_analysis(client, coach, match, fake_ai):
    links = (
        link(12, 31, 6, 15),
        link(12, 40, 6, 30),                 # 12 already continues in 31 (one to one)
        link(5, 99, 33, 40),                 # a track without detections
        link(31, 40, 18, 10),                # goes back in time
        {"from_track": 8, "to_track": 40},   # incomplete
    )
    kits = (kit(7), kit(7), kit(99), {**kit(8), "kit_color": "cyan"})
    analysis_id = analysed(client, coach, match, links=links, kits=kits)
    assert client.get(f"/api/analyses/{analysis_id}", headers=coach["headers"]).json()["status"] == "COMPLETED"
    body = hints(client, coach, analysis_id)
    assert [(item["from_track"], item["to_track"]) for item in body["links"]] == [(12, 31)]
    assert body["kits"][0]["tracks"] == [7]


def test_accepting_a_link_gives_the_number_to_the_whole_chain(client, coach, analyst, team, match, fake_ai):
    player = squad_player(client, coach, team, 10)
    analysis_id = analysed(client, coach, match, links=CHAIN)
    assert identity(client, analyst, analysis_id, 12, shirt_number=10).json()["tracks"] == [12]

    accepted = decide(client, analyst, analysis_id, 12, "ACCEPTED")
    assert accepted.status_code == 200 and accepted.json()["tracks"] == [12, 31]
    decide(client, analyst, analysis_id, 31, "ACCEPTED")
    assert {t: numbers(client, coach, analysis_id)[t] for t in (12, 31, 40)} == {t: ("PLAYER", 10) for t in (12, 31, 40)}
    assert hints(client, coach, analysis_id)["same_player"] == {"12": 12, "31": 12, "40": 12}
    assert ranking(client, coach, team)[10]["detections"] == 7  # 3 + 2 + 2 detections are all his
    assert player["shirt_number"] == 10


def test_a_number_typed_on_one_track_goes_to_the_tracks_already_joined(client, coach, match, fake_ai):
    analysis_id = analysed(client, coach, match, links=CHAIN)
    decide(client, coach, analysis_id, 12, "ACCEPTED")
    assert identity(client, coach, analysis_id, 31, shirt_number=23).json()["tracks"] == [12, 31]
    assert numbers(client, coach, analysis_id)[12] == ("PLAYER", 23)
    assert numbers(client, coach, analysis_id)[40] == ("PLAYER", None)  # not joined: the link is only suggested


def test_two_tracks_identified_as_different_people_cannot_be_joined(client, coach, match, fake_ai):
    analysis_id = analysed(client, coach, match, links=CHAIN)
    identity(client, coach, analysis_id, 12, shirt_number=10)
    identity(client, coach, analysis_id, 31, shirt_number=7)
    refused = decide(client, coach, analysis_id, 12, "ACCEPTED")
    assert refused.status_code == 409 and refused.json()["code"] == "TRACK_IDENTITY_CONFLICT"
    assert hints(client, coach, analysis_id)["links"][0]["status"] == "SUGGESTED"
    assert numbers(client, coach, analysis_id)[31] == ("PLAYER", 7)


def test_a_rejected_or_undone_link_does_not_join(client, coach, match, fake_ai):
    analysis_id = analysed(client, coach, match, links=CHAIN)
    decide(client, coach, analysis_id, 12, "REJECTED")
    assert identity(client, coach, analysis_id, 12, shirt_number=9).json()["tracks"] == [12]
    decide(client, coach, analysis_id, 12, "ACCEPTED")
    decide(client, coach, analysis_id, 12, "SUGGESTED")
    link_12 = hints(client, coach, analysis_id)["links"][0]
    assert (link_12["status"], link_12["decided_at"]) == ("SUGGESTED", None)
    assert decide(client, coach, analysis_id, 77, "ACCEPTED").status_code == 404


def test_a_kit_is_marked_once_for_all_its_tracks_or_dismissed(client, coach, match, fake_ai):
    analysis_id = analysed(client, coach, match, kits=REFEREE_KIT)
    marked = client.put(f"/api/analyses/{analysis_id}/kits/1/identity", headers=coach["headers"], json={"role": "REFEREE"})
    assert marked.status_code == 200 and marked.json()["tracks"] == [7, 8]
    assert numbers(client, coach, analysis_id)[7] == ("REFEREE", None) == numbers(client, coach, analysis_id)[8]

    dismissed = client.put(f"/api/analyses/{analysis_id}/kits/1", headers=coach["headers"], json={"dismissed": True})
    assert dismissed.json()["dismissed"] is True and hints(client, coach, analysis_id)["kits"][0]["dismissed"] is True
    client.put(f"/api/analyses/{analysis_id}/kits/1", headers=coach["headers"], json={"dismissed": False})
    assert hints(client, coach, analysis_id)["kits"][0]["dismissed"] is False
    assert client.put(f"/api/analyses/{analysis_id}/kits/9", headers=coach["headers"],
                      json={"dismissed": True}).status_code == 404


def test_the_goalkeeper_kit_gets_his_number_in_every_track(client, coach, team, match, fake_ai):
    keeper = squad_player(client, coach, team, 1)
    analysis_id = analysed(client, coach, match, kits=(kit(7, color="#d16422"), kit(8, color="#d16422")))
    body = client.put(f"/api/analyses/{analysis_id}/kits/1/identity", headers=coach["headers"],
                      json={"role": "PLAYER", "shirt_number": 1}).json()
    assert body["player_id"] == keeper["id"] and ranking(client, coach, team)[1]["detections"] == 4


def test_another_team_sees_and_decides_nothing(client, coach, match, fake_ai):
    analysis_id = analysed(client, coach, match, links=CHAIN, kits=REFEREE_KIT)
    other = register(client, "otro.entrenador@club.com", "COACH")
    client.post("/api/teams", headers=other["headers"], json={"name": "Otro Club", "category": "Sub-17", "city": "Pasto"})
    assert client.get(f"/api/analyses/{analysis_id}/identification-hints", headers=other["headers"]).status_code == 404
    assert decide(client, other, analysis_id, 12, "ACCEPTED").status_code == 404
    assert client.put(f"/api/analyses/{analysis_id}/kits/1", headers=other["headers"],
                      json={"dismissed": True}).status_code == 404
    assert hints(client, coach, analysis_id)["links"][0]["status"] == "SUGGESTED"
