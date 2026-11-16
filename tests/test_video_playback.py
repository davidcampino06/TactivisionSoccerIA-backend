"""Watching the uploaded video again, with what the AI saw drawn on top."""

from conftest import register
from test_clip_library import analyse, upload
from test_video_analysis import FakeClient, fake_ai, fake_payload  # noqa: F401  (fixtures)

from config import settings


def link(client, who, video):
    return client.post(f"/api/videos/{video['id']}/playback", headers=who["headers"])


def test_the_uploaded_video_can_be_watched_again_through_a_temporary_link(client, coach, analyst, match):
    video = upload(client, coach, match)
    body = link(client, analyst, video).json()
    assert body["media_type"] == "video/mp4" and body["expires_in_seconds"] == 7200
    played = client.get(body["url"])  # no session header: a <video> element cannot send one
    assert played.status_code == 200 and played.content == b"fake-bytes"
    assert played.headers["content-type"] == "video/mp4" and played.headers["cache-control"].startswith("private")


def test_the_player_can_jump_inside_the_video(client, coach, match):
    video = upload(client, coach, match)
    url = link(client, coach, video).json()["url"]
    part = client.get(url, headers={"Range": "bytes=5-9"})
    assert part.status_code == 206 and part.content == b"bytes"
    assert part.headers["content-range"] == "bytes 5-9/10"


def test_a_link_only_plays_its_own_video_and_other_tokens_do_not_work(client, coach, match):
    first, second = upload(client, coach, match), upload(client, coach, match)
    token = link(client, coach, first).json()["url"].split("token=")[1]
    assert client.get(f"/api/videos/{second['id']}/stream?token={token}").status_code == 401
    assert client.get(f"/api/videos/{first['id']}/stream?token=not-a-real-token").status_code == 401
    assert client.get(f"/api/videos/{first['id']}/stream").status_code == 422
    session = coach["headers"]["Authorization"].removeprefix("Bearer ")
    assert client.get(f"/api/videos/{first['id']}/stream?token={session}").status_code == 401  # wrong purpose


def test_only_people_of_the_team_get_a_link(client, coach, match):
    video = upload(client, coach, match)
    outsider = register(client, "otro@club.com", "COACH")
    client.post("/api/teams", headers=outsider["headers"], json={"name": "Otro club"})
    assert link(client, outsider, video).status_code in (403, 404)
    assert client.post(f"/api/videos/{video['id']}/playback").status_code == 401


def test_a_video_whose_file_was_lost_says_so(client, coach, match):
    video = upload(client, coach, match)
    url = link(client, coach, video).json()["url"]
    for stored in settings.upload_dir.iterdir():
        stored.unlink()
    assert link(client, coach, video).json()["code"] == "VIDEO_FILE_MISSING"
    assert client.get(url).status_code == 409


def test_the_overlay_groups_what_the_ai_saw_by_frame(client, coach, match, fake_ai):
    video = upload(client, coach, match)
    analysis_id = analyse(client, coach, video, fake_payload())
    overlay = client.get(f"/api/analyses/{analysis_id}/overlay", headers=coach["headers"]).json()
    times = [frame[0] for frame in overlay["frames"]]
    assert times == sorted(times) and len(times) == len(set(times)) and overlay["until"] == times[-1]
    boxes = [box for _, frame in overlay["frames"] for box in frame]
    assert all(len(box) == 7 and box[5] in ("P", "B", "O") for box in boxes)
    tracked = [box for box in boxes if box[4] is not None]
    assert {box[4] for box in tracked} == {t["track_id"] for t in client.get(
        f"/api/analyses/{analysis_id}/tracks", headers=coach["headers"]).json()}
    outsider = register(client, "otro@club.com", "COACH")
    client.post("/api/teams", headers=outsider["headers"], json={"name": "Otro club"})
    assert client.get(f"/api/analyses/{analysis_id}/overlay", headers=outsider["headers"]).status_code in (403, 404)
