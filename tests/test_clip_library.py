"""Situation of each clip (migration 0020) and the clip library with its inverted index."""

from conftest import register
from services.clip_library import ClipIndex
from test_review_inbox import with_own_team
from test_video_analysis import FakeClient, fake_ai, fake_payload  # noqa: F401  (fixtures)

PROBLEM = "Possible tactical issue: excessive distance between defensive and midfield lines".capitalize()


def new_match(client, coach, team, opponent, date):
    return client.post(f"/api/teams/{team['id']}/matches", headers=coach["headers"],
                       json={"opponent": opponent, "match_date": date}).json()


def upload(client, coach, match, **form):
    response = client.post(f"/api/matches/{match['id']}/videos", headers=coach["headers"], data=form,
                           files={"video": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert response.status_code == 201, response.text
    return response.json()


def analyse(client, coach, video, payload):
    FakeClient.response = payload
    return client.post(f"/api/videos/{video['id']}/analysis", headers=coach["headers"], json={}).json()["id"]


def library(client, coach, team):
    response = client.get(f"/api/teams/{team['id']}/clip-library", headers=coach["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def test_a_person_says_which_situation_a_clip_shows(client, coach, analyst, match):
    video = upload(client, coach, match, situation="BUILD_UP", situation_note="  Salida por la izquierda  ")
    assert (video["situation"], video["situation_note"]) == ("BUILD_UP", "Salida por la izquierda")
    changed = client.patch(f"/api/videos/{video['id']}", headers=analyst["headers"],
                           json={"situation": "PRESSING", "situation_note": "   "}).json()
    assert (changed["situation"], changed["situation_note"]) == ("PRESSING", None)
    cleared = client.patch(f"/api/videos/{video['id']}", headers=analyst["headers"], json={"situation": None}).json()
    assert cleared["situation"] is None


def test_unknown_situations_and_long_notes_are_rejected(client, coach, match):
    bad = client.post(f"/api/matches/{match['id']}/videos", headers=coach["headers"], data={"situation": "DANCE"},
                      files={"video": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert bad.status_code == 422 and bad.json()["code"] == "INVALID_SITUATION"
    video = upload(client, coach, match)
    assert client.patch(f"/api/videos/{video['id']}", headers=coach["headers"],
                        json={"situation": "BUILD_UP", "situation_note": "x" * 201}).status_code == 422


def test_the_library_lists_analysed_clips_of_our_team_with_counts(client, coach, team, fake_ai):
    first = new_match(client, coach, team, "Nacional", "2026-09-01T15:00:00")
    second = new_match(client, coach, team, "Medellín", "2026-09-08T15:00:00")
    build_up = upload(client, coach, first, situation="BUILD_UP")
    pressing = upload(client, coach, second, situation="PRESSING")
    upload(client, coach, second, situation="BUILD_UP")  # not analysed: not in the library
    analyse(client, coach, build_up, with_own_team("TEAM_A"))
    analyse(client, coach, pressing, with_own_team("TEAM_B"))  # the problem and strength are the rival's

    data = library(client, coach, team)
    assert [(c["match"]["opponent"], c["situation"]) for c in data["clips"]] == [("Medellín", "PRESSING"), ("Nacional", "BUILD_UP")]
    pressing_clip, build_up_clip = data["clips"]
    assert pressing_clip["problems"] == [] and pressing_clip["strengths"] == []
    assert [p["title"] for p in build_up_clip["problems"]] == [PROBLEM]
    assert build_up_clip["problems"][0]["status"] == "GENERATED"
    assert build_up_clip["strengths"][0]["title"] == "Siempre con un compañero cerca"
    assert data["facets"]["situations"] == [{"key": "BUILD_UP", "count": 1, "clips": [build_up["id"]]},
                                            {"key": "PRESSING", "count": 1, "clips": [pressing["id"]]}]
    assert data["facets"]["problems"] == [{"key": PROBLEM, "count": 1, "clips": [build_up["id"]]}]


def test_dismissed_items_do_not_count_in_the_filters(client, coach, team, fake_ai):
    match = new_match(client, coach, team, "Nacional", "2026-09-01T15:00:00")
    video = upload(client, coach, match)
    analysis_id = analyse(client, coach, video, fake_payload())
    result = client.get(f"/api/analyses/{analysis_id}/result", headers=coach["headers"]).json()
    client.patch(f"/api/recommendations/{result['recommendations'][0]['id']}", headers=coach["headers"],
                 json={"action": "dismiss"})
    data = library(client, coach, team)
    assert data["facets"]["problems"] == [] and data["facets"]["situations"] == [{"key": "NONE", "count": 1, "clips": [video["id"]]}]
    assert data["clips"][0]["problems"][0]["status"] == "DISMISSED"  # still shown, labelled


def test_the_library_is_private(client, team):
    outsider = register(client, "otro@club.com", "COACH")
    client.post("/api/teams", headers=outsider["headers"], json={"name": "Otro club"})
    assert client.get(f"/api/teams/{team['id']}/clip-library", headers=outsider["headers"]).status_code in (403, 404)


def test_the_index_answers_with_one_lookup_and_counts():
    index = ClipIndex()
    for clip, keys in (("a", ["situation:BUILD_UP", "problem:X"]), ("b", ["situation:BUILD_UP"]), ("c", ["problem:X"])):
        for key in keys:
            index.add(key, clip)
    index.add("problem:X", "c")  # the same clip twice counts once
    assert index.clips("problem:X") == ["a", "c"] and index.clips("problem:Y") == []
    assert index.counts("situation:") == [{"key": "BUILD_UP", "count": 2, "clips": ["a", "b"]}]


def test_each_clip_says_if_it_can_be_watched_and_shows_photos_of_its_players(client, coach, team, fake_ai):
    import base64, io
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (20, 40), (200, 30, 30)).save(out, "JPEG")
    match = new_match(client, coach, team, "Nacional", "2026-09-01T15:00:00")
    video = upload(client, coach, match)
    payload = fake_payload()
    payload["track_snapshots"] = [{"track_id": 1, "frame_number": 0, "timestamp": 0.0, "confidence": 0.9, "width": 20,
                                   "height": 40, "image_jpeg_base64": base64.b64encode(out.getvalue()).decode()}]
    analyse(client, coach, video, payload)
    (clip,) = library(client, coach, team)["clips"]
    assert clip["file_available"] is True and clip["photos"] == [1]
