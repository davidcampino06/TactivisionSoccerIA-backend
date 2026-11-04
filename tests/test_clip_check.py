"""Clip check before the analysis: the backend asks the AI and never stores or blocks anything."""

from services.ai_client import AIServiceError, HttpClipCheckClient

REPORT = {"verdict": "warn", "video": {"fps": 30.0, "frame_count": 780, "width": 1920, "height": 1080,
                                       "duration_seconds": 26.0},
          "sampled_frames": 8,
          "checks": [{"code": "coverage", "status": "warn", "measured": True, "title": "Dura 26 s",
                      "detail": "El modo rápido solo analiza los primeros 20 s.", "value": {"duration": 26.0}}]}


def upload(client, coach, match):
    return client.post(f"/api/matches/{match['id']}/videos", headers=coach["headers"],
                       files={"video": ("clip.mp4", b"fake-bytes", "video/mp4")}).json()


def test_the_coach_gets_the_ai_report_and_the_modes_it_covers(client, coach, match, monkeypatch):
    sent = {}

    def fake_post(self, path, **kwargs):
        sent.update(path=path, data=kwargs["data"])
        return REPORT
    monkeypatch.setattr(HttpClipCheckClient, "_post", fake_post)
    video = upload(client, coach, match)
    response = client.post(f"/api/videos/{video['id']}/quality", headers=coach["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["checks"][0]["code"] == "coverage"
    assert sent["path"] == "/api/video-quality"
    assert sent["data"] == {"fast_stride": "5", "fast_max_frames": "120", "full_stride": "3", "full_max_frames": "300"}


def test_ai_down_and_missing_file_give_clear_errors(client, coach, match, monkeypatch):
    def down(self, path, **kwargs):
        raise AIServiceError("AI Service unreachable", "No se pudo contactar el servicio de IA.")
    monkeypatch.setattr(HttpClipCheckClient, "_post", down)
    video = upload(client, coach, match)
    response = client.post(f"/api/videos/{video['id']}/quality", headers=coach["headers"])
    assert response.status_code == 503 and response.json()["code"] == "AI_UNAVAILABLE"

    from config import settings
    for stored in settings.upload_dir.glob("*.mp4"):
        stored.unlink()
    response = client.post(f"/api/videos/{video['id']}/quality", headers=coach["headers"])
    assert response.status_code == 409 and response.json()["code"] == "VIDEO_FILE_MISSING"


def test_the_check_is_private(client, coach, match):
    from conftest import register
    video = upload(client, coach, match)
    outsider = register(client, "otro@club.com", "COACH")
    client.post("/api/teams", headers=outsider["headers"], json={"name": "Otro club"})
    assert client.post(f"/api/videos/{video['id']}/quality", headers=outsider["headers"]).status_code == 404
