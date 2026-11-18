"""Administrator: permanently delete a team (with its content and its people) or a single account."""

import database
import rls
from config import settings
from conftest import DEFAULT_PASSWORD, register
from models import Video, VideoAnalysis


def upload(client, coach, match):
    response = client.post(f"/api/matches/{match['id']}/videos", headers=coach["headers"],
                           files={"video": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert response.status_code == 201, response.text
    return response.json()


def video_path(video_id: str):
    with database.SessionLocal() as db:
        rls.mark_system(db)
        return settings.upload_dir / db.get(Video, video_id).file_path


def user_ids(client, admin):
    return {user["email"]: user["id"] for user in client.get("/api/admin/users", headers=admin["headers"]).json()}


def test_deleting_a_team_removes_its_content_its_people_and_its_files(client, admin, coach, team, analyst, match):
    client.post(f"/api/teams/{team['id']}/players", headers=coach["headers"], json={"first_name": "A", "last_name": "B"})
    video = upload(client, coach, match)
    stored = video_path(video["id"])
    assert stored.is_file()
    # Another team and a free account must not be touched.
    other = register(client, "otro@test.com", "COACH")
    other_team = client.post("/api/teams", headers=other["headers"], json={"name": "Nacional Sub-17"}).json()
    register(client, "libre@test.com", "ANALYST")

    deleted = client.delete(f"/api/admin/teams/{team['id']}", headers=admin["headers"])
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"team": "Barcelona Juvenil", "players": 1, "matches": 1, "videos": 1,
                              "users": 2, "files_removed": 1}
    assert not stored.exists()

    teams = client.get("/api/admin/teams", headers=admin["headers"]).json()
    assert [item["id"] for item in teams] == [other_team["id"]]
    assert set(user_ids(client, admin)) == {"admin@test.com", "otro@test.com", "libre@test.com"}
    login = client.post("/api/auth/login", json={"email": "coach@test.com", "password": DEFAULT_PASSWORD})
    assert login.status_code == 401
    # The surviving coach still sees his own team.
    assert client.get("/api/teams/mine", headers=other["headers"]).json()["id"] == other_team["id"]


def test_a_team_with_an_analysis_in_progress_is_not_deleted(client, admin, coach, team, match):
    video = upload(client, coach, match)
    with database.SessionLocal() as db:
        rls.mark_system(db)
        db.add(VideoAnalysis(video_id=video["id"], status="PROCESSING"))
        db.commit()
    response = client.delete(f"/api/admin/teams/{team['id']}", headers=admin["headers"])
    assert response.status_code == 409 and response.json()["code"] == "TEAM_ANALYSIS_RUNNING"
    assert len(client.get("/api/admin/teams", headers=admin["headers"]).json()) == 1


def test_deleting_accounts(client, admin, coach, team, analyst):
    ids = user_ids(client, admin)

    gone = client.delete(f"/api/admin/users/{ids['analyst@test.com']}", headers=admin["headers"])
    assert gone.status_code == 200 and gone.json() == {"email": "analyst@test.com", "role": "ANALYST"}
    assert "analyst@test.com" not in user_ids(client, admin)
    assert client.get("/api/admin/teams", headers=admin["headers"]).json()[0]["analysts"] == 0

    owner = client.delete(f"/api/admin/users/{ids['coach@test.com']}", headers=admin["headers"])
    assert owner.status_code == 409 and owner.json()["code"] == "COACH_OWNS_TEAM"
    itself = client.delete(f"/api/admin/users/{ids['admin@test.com']}", headers=admin["headers"])
    assert itself.status_code == 403 and itself.json()["code"] == "ADMIN_MANAGED_BY_CONFIG"
    missing = client.delete("/api/admin/users/no-existe", headers=admin["headers"])
    assert missing.status_code == 404


def test_only_the_administrator_deletes(client, coach, team, analyst):
    for account in (coach, analyst):
        for path in (f"/api/admin/teams/{team['id']}", f"/api/admin/users/{coach['user']['id']}"):
            response = client.delete(path, headers=account["headers"])
            assert response.status_code == 403 and response.json()["code"] == "ROLE_NOT_ALLOWED"
    assert client.get("/api/teams/mine", headers=coach["headers"]).status_code == 200
