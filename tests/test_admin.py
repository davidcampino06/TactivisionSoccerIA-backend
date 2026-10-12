"""Administration panel: totals, users and teams (counts only, never tactical content)."""

from conftest import register


def test_overview_counts_across_teams(client, admin, coach, team, match, analyst):
    client.post(f"/api/teams/{team['id']}/players", headers=coach["headers"], json={"first_name": "A", "last_name": "B"})
    overview = client.get("/api/admin/overview", headers=admin["headers"])
    assert overview.status_code == 200, overview.text
    data = overview.json()
    assert data["users"]["by_role"] == {"ADMINISTRATOR": 1, "COACH": 1, "ANALYST": 1}
    assert data["teams"] == 1 and data["matches"] == 1  # read across teams despite Row-Level Security
    assert len(data["users"]["signups"]) == 14 and data["users"]["signups"][-1]["count"] == 3
    assert data["queue"]["waiting"] == 0 and data["queue"]["jobs"] == []
    assert data["system"]["database"] == "CONNECTED" and data["system"]["row_level_security"] is True
    assert "indicators" not in overview.text and "recommendation" not in overview.text


def test_teams_show_counts_and_coach(client, admin, coach, team, match, analyst):
    client.post(f"/api/teams/{team['id']}/players", headers=coach["headers"], json={"first_name": "A", "last_name": "B"})
    teams = client.get("/api/admin/teams", headers=admin["headers"]).json()
    assert teams[0]["name"] == "Barcelona Juvenil" and teams[0]["coach_name"] == "Test Coach"
    assert (teams[0]["analysts"], teams[0]["players"], teams[0]["matches"], teams[0]["analyses"]) == (1, 1, 1, 0)


def test_users_search_and_team_names(client, admin, coach, team, analyst):
    register(client, "libre@test.com", "ANALYST")
    users = client.get("/api/admin/users?q=analyst@", headers=admin["headers"]).json()
    assert {user["email"] for user in users} == {"analyst@test.com"}
    everyone = {user["email"]: user["team_name"] for user in client.get("/api/admin/users", headers=admin["headers"]).json()}
    assert everyone["coach@test.com"] == "Barcelona Juvenil" and everyone["analyst@test.com"] == "Barcelona Juvenil"
    assert everyone["libre@test.com"] is None

    free = next(u for u in client.get("/api/admin/users?role=analyst", headers=admin["headers"]).json() if u["email"] == "libre@test.com")
    changed = client.patch(f"/api/admin/users/{free['id']}", headers=admin["headers"], json={"role": "COACH"})
    assert changed.status_code == 200 and changed.json()["role"] == "COACH"


def test_only_the_administrator(client, coach, analyst):
    for path in ("/api/admin/overview", "/api/admin/users", "/api/admin/teams"):
        for account in (coach, analyst):
            response = client.get(path, headers=account["headers"])
            assert response.status_code == 403 and response.json()["code"] == "ROLE_NOT_ALLOWED"
