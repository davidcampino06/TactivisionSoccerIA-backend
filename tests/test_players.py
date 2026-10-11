"""Squad management: player details, shirt numbers, withdrawals and reactivation."""


def players_url(team):
    return f"/api/teams/{team['id']}/players"


def test_player_has_preferred_foot(client, coach, team):
    created = client.post(players_url(team), headers=coach["headers"], json={
        "first_name": "Luis", "last_name": "Díaz", "shirt_number": 7, "position": "FORWARD", "preferred_foot": "LEFT"})
    assert created.status_code == 201, created.text
    assert created.json()["preferred_foot"] == "LEFT"

    updated = client.put(f"/api/players/{created.json()['id']}", headers=coach["headers"], json={"preferred_foot": "BOTH"})
    assert updated.json()["preferred_foot"] == "BOTH"

    wrong = client.post(players_url(team), headers=coach["headers"],
                        json={"first_name": "A", "last_name": "B", "preferred_foot": "HAND"})
    assert wrong.status_code == 422


def test_shirt_number_taken_has_code(client, coach, team):
    client.post(players_url(team), headers=coach["headers"], json={"first_name": "A", "last_name": "B", "shirt_number": 9})
    taken = client.post(players_url(team), headers=coach["headers"],
                        json={"first_name": "C", "last_name": "D", "shirt_number": 9})
    assert taken.status_code == 409
    assert taken.json()["code"] == "SHIRT_NUMBER_TAKEN" and taken.json()["shirt_number"] == 9


def test_inactive_only_through_remove(client, coach, team):
    player = client.post(players_url(team), headers=coach["headers"], json={"first_name": "A", "last_name": "B"}).json()
    response = client.put(f"/api/players/{player['id']}", headers=coach["headers"], json={"status": "INACTIVE"})
    assert response.status_code == 409 and response.json()["code"] == "PLAYER_REMOVE_REQUIRES_REASON"


def test_reactivation_reopens_history_and_checks_shirt(client, coach, team):
    h = coach["headers"]
    old = client.post(players_url(team), headers=h, json={"first_name": "A", "last_name": "B", "shirt_number": 5}).json()
    client.request("DELETE", f"/api/players/{old['id']}", headers=h, json={"withdrawal_reason": "Préstamo"})

    # The number is free again while the player is out of the squad
    newcomer = client.post(players_url(team), headers=h, json={"first_name": "C", "last_name": "D", "shirt_number": 5})
    assert newcomer.status_code == 201

    blocked = client.put(f"/api/players/{old['id']}", headers=h, json={"status": "ACTIVE"})
    assert blocked.status_code == 409 and blocked.json()["code"] == "SHIRT_NUMBER_TAKEN"

    back = client.put(f"/api/players/{old['id']}", headers=h, json={"status": "ACTIVE", "shirt_number": 15})
    assert back.status_code == 200 and back.json()["status"] == "ACTIVE"
    history = client.get(f"/api/players/{old['id']}/history", headers=h).json()
    assert len(history) == 2 and history[0]["withdrawal_reason"] == "Préstamo" and history[1]["left_at"] is None


def test_squad_listing_and_roles(client, coach, team, analyst):
    h = coach["headers"]
    active = client.post(players_url(team), headers=h, json={"first_name": "A", "last_name": "B"}).json()
    gone = client.post(players_url(team), headers=h, json={"first_name": "C", "last_name": "D"}).json()
    client.request("DELETE", f"/api/players/{gone['id']}", headers=h, json={"withdrawal_reason": "Fin de contrato"})

    assert [p["id"] for p in client.get(players_url(team), headers=analyst["headers"]).json()] == [active["id"]]
    everyone = client.get(players_url(team) + "?include_inactive=true", headers=analyst["headers"]).json()
    assert {p["id"] for p in everyone} == {active["id"], gone["id"]}

    denied = client.post(players_url(team), headers=analyst["headers"], json={"first_name": "X", "last_name": "Y"})
    assert denied.status_code == 403 and denied.json()["code"] == "ROLE_NOT_ALLOWED"
    assert client.get(f"/api/players/{active['id']}/appearances", headers=analyst["headers"]).json() == []


def test_errors_carry_codes(client, coach, team):
    other = client.post("/api/teams", headers=coach["headers"], json={"name": "Otro equipo"})
    assert other.status_code == 409 and other.json()["code"] == "COACH_HAS_TEAM"

    from conftest import register
    newcomer = register(client, "nuevo@test.com", "ANALYST")
    bad = client.post("/api/teams/join", headers=newcomer["headers"], json={"invitation_code": "NOEXISTE"})
    assert bad.status_code == 404 and bad.json()["code"] == "INVALID_INVITATION_CODE"
    assert client.get("/api/teams/mine", headers=newcomer["headers"]).json()["code"] == "NO_TEAM"

    match = client.post(f"/api/teams/{team['id']}/matches", headers=coach["headers"],
                        json={"opponent": "Rival", "match_date": "2026-09-01T15:00:00"}).json()
    compare = client.get(f"/api/teams/{team['id']}/comparisons?match_ids={match['id']}", headers=coach["headers"])
    assert compare.status_code == 400 and compare.json()["code"] == "COMPARE_MIN_MATCHES"
