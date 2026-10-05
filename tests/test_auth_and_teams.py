from tests.conftest import register


def test_status_keeps_prototype_contract(client):
    body = client.get("/api/status").json()
    assert body["backend"] == "OK"
    assert body["database"] == "CONNECTED"
    assert body["ai_service"] == "UNREACHABLE"


def test_cannot_self_register_as_administrator(client):
    response = client.post("/api/auth/register", json={
        "first_name": "A", "last_name": "B", "email": "x@test.com", "password": "Password123", "role": "ADMINISTRATOR"})
    assert response.status_code == 422


def test_login_and_wrong_password(client, coach):
    assert client.post("/api/auth/login", json={"email": "coach@test.com", "password": "Password123"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "coach@test.com", "password": "wrong-pass"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_password_recovery_flow_is_single_use(client, coach):
    token = client.post("/api/auth/password-recovery", json={"email": "coach@test.com"}).json()["reset_token"]
    assert client.post("/api/auth/password-reset", json={"token": token, "new_password": "NewPassword456"}).status_code == 204
    assert client.post("/api/auth/password-reset", json={"token": token, "new_password": "Other789xyz"}).status_code == 400
    assert client.post("/api/auth/login", json={"email": "coach@test.com", "password": "NewPassword456"}).status_code == 200


def test_coach_owns_one_team_and_invitation_code_format(client, coach, team):
    assert team["invitation_code"].startswith("BARCE-")
    second = client.post("/api/teams", headers=coach["headers"], json={"name": "Other"})
    assert second.status_code == 409


def test_analyst_access_rules(client, team, analyst):
    assert client.get(f"/api/teams/{team['id']}", headers=analyst["headers"]).json()["invitation_code"] is None
    assert client.get(f"/api/teams/{team['id']}/players", headers=analyst["headers"]).status_code == 200
    forbidden = client.post(f"/api/teams/{team['id']}/players", headers=analyst["headers"],
                            json={"first_name": "A", "last_name": "B"})
    assert forbidden.status_code == 403
    again = client.post("/api/teams/join", headers=analyst["headers"], json={"invitation_code": team["invitation_code"]})
    assert again.status_code == 409


def test_invalid_invitation_code(client, team):
    other = register(client, "other.analyst@test.com", "ANALYST")
    assert client.post("/api/teams/join", headers=other["headers"], json={"invitation_code": "FAKE-0000"}).status_code == 404
    assert client.get(f"/api/teams/{team['id']}", headers=other["headers"]).status_code == 403


def test_other_coach_cannot_access_team(client, team):
    intruder = register(client, "intruder@test.com", "COACH")
    assert client.get(f"/api/teams/{team['id']}/matches", headers=intruder["headers"]).status_code == 403


def test_admin_sees_teams_but_not_tactical_content(client, admin, team, match):
    teams = client.get("/api/admin/teams", headers=admin["headers"]).json()
    assert teams[0]["name"] == "Barcelona Juvenil" and "invitation_code" not in teams[0]
    assert client.get(f"/api/teams/{team['id']}/players", headers=admin["headers"]).status_code == 403
    assert client.get(f"/api/matches/{match['id']}", headers=admin["headers"]).status_code == 403
    assert client.post("/api/teams", headers=admin["headers"], json={"name": "X Team"}).status_code == 403


def test_admin_can_deactivate_user(client, admin, coach):
    users = client.get("/api/admin/users?role=COACH", headers=admin["headers"]).json()
    response = client.patch(f"/api/admin/users/{users[0]['id']}", headers=admin["headers"], json={"is_active": False})
    assert response.json()["is_active"] is False
    assert client.get("/api/auth/me", headers=coach["headers"]).status_code == 401


def test_players_and_history(client, coach, team):
    url = f"/api/teams/{team['id']}/players"
    player = client.post(url, headers=coach["headers"], json={"first_name": "Juan", "last_name": "Perez", "shirt_number": 10}).json()
    assert client.post(url, headers=coach["headers"], json={"first_name": "B", "last_name": "C", "shirt_number": 10}).status_code == 409
    removed = client.request("DELETE", f"/api/players/{player['id']}", headers=coach["headers"],
                             json={"withdrawal_reason": "Transferred"})
    assert removed.json()["status"] == "INACTIVE"
    history = client.get(f"/api/players/{player['id']}/history", headers=coach["headers"]).json()
    assert history[0]["left_at"] is not None and history[0]["withdrawal_reason"] == "Transferred"
