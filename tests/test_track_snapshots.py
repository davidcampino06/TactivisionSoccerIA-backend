"""Photo of each detected track (migration 0021): what the staff looks at to tell who is who."""

import base64
import io

from PIL import Image

from conftest import register
from test_clip_library import analyse, upload
from test_video_analysis import FakeClient, fake_ai, fake_payload  # noqa: F401  (fixtures)

import database
import rls
from models import TrackSnapshot


def jpeg(color=(200, 30, 30), size=(36, 80)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "JPEG", quality=80)
    return out.getvalue()


def snapshot(track_id=1, data: bytes | str | None = None, **extra):
    raw = data if data is not None else jpeg()
    encoded = raw if isinstance(raw, str) else base64.b64encode(raw).decode()
    return {"track_id": track_id, "frame_number": 3, "timestamp": 0.12, "confidence": 0.88, "width": 36, "height": 80,
            "image_jpeg_base64": encoded, **extra}


def analysed(client, coach, match, snapshots):
    payload = fake_payload()
    payload["track_snapshots"] = snapshots
    video = upload(client, coach, match)
    return analyse(client, coach, video, payload), video


def tracks_of(client, coach, analysis_id):
    return client.get(f"/api/analyses/{analysis_id}/tracks", headers=coach["headers"]).json()


def test_the_photo_of_a_track_is_saved_and_served_as_a_jpeg(client, coach, match, fake_ai):
    original = jpeg()
    analysis_id, _ = analysed(client, coach, match, [snapshot(1, original)])
    response = client.get(f"/api/analyses/{analysis_id}/tracks/1/snapshot", headers=coach["headers"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg" and response.content == original
    assert response.headers["cache-control"].startswith("private")
    assert Image.open(io.BytesIO(response.content)).size == (36, 80)


def test_the_track_list_says_which_tracks_have_a_photo_and_when_they_appear(client, coach, match, fake_ai):
    analysis_id, _ = analysed(client, coach, match, [snapshot(1)])
    (track,) = tracks_of(client, coach, analysis_id)
    assert track["has_snapshot"] is True and track["snapshot_seconds"] == 0.12
    assert (track["first_seconds"], track["last_seconds"]) == (0.0, 0.12)


def test_an_analysis_without_photos_still_lists_its_tracks(client, coach, match, fake_ai):
    """Analyses from before the photos (or an AI service that does not send them)."""
    analysis_id, _ = analysed(client, coach, match, [])
    (track,) = tracks_of(client, coach, analysis_id)
    assert track["has_snapshot"] is False and track["snapshot_seconds"] is None and track["detections"] == 2
    missing = client.get(f"/api/analyses/{analysis_id}/tracks/1/snapshot", headers=coach["headers"])
    assert missing.status_code == 404


def test_a_bad_photo_is_skipped_and_never_fails_the_analysis(client, coach, match, fake_ai):
    junk = [
        snapshot(1, "esto no es base64!!"),                  # not base64
        snapshot(1, b"GIF89a-not-a-jpeg"),                   # not a JPEG
        snapshot(99, jpeg()),                                # a track with no detections
        snapshot(1, b"\xff\xd8\xff" + b"0" * 70_000),        # too big
    ]
    analysis_id, video = analysed(client, coach, match, junk)
    status = client.get(f"/api/analyses/{analysis_id}", headers=coach["headers"]).json()["status"]
    assert status == "COMPLETED"
    assert tracks_of(client, coach, analysis_id)[0]["has_snapshot"] is False


def test_only_people_of_the_team_can_see_the_photos(client, coach, analyst, match, fake_ai):
    analysis_id, _ = analysed(client, coach, match, [snapshot(1)])
    assert client.get(f"/api/analyses/{analysis_id}/tracks/1/snapshot", headers=analyst["headers"]).status_code == 200
    outsider = register(client, "otro@club.com", "COACH")
    client.post("/api/teams", headers=outsider["headers"], json={"name": "Otro club"})
    assert client.get(f"/api/analyses/{analysis_id}/tracks/1/snapshot", headers=outsider["headers"]).status_code in (403, 404)
    assert client.get(f"/api/analyses/{analysis_id}/tracks/1/snapshot").status_code == 401


def test_the_photos_go_away_with_the_video(client, coach, match, fake_ai):
    analysis_id, video = analysed(client, coach, match, [snapshot(1)])
    assert client.delete(f"/api/videos/{video['id']}", headers=coach["headers"]).status_code in (200, 204)
    with rls.mark_system(database.SessionLocal()) as db:
        assert db.query(TrackSnapshot).filter(TrackSnapshot.analysis_id == analysis_id).count() == 0
