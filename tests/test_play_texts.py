"""Limits of a play's texts and the action types written by the team (migration 0022)."""

from conftest import register


def create(client, coach, team, **fields):
    return client.post(f"/api/teams/{team['id']}/tactical-plays", headers=coach["headers"],
                       json={"name": "Salida por banda", **fields})


def types(client, who, team):
    return client.get(f"/api/teams/{team['id']}/action-types", headers=who["headers"]).json()


def test_a_play_name_has_up_to_50_characters_and_its_description_up_to_100(client, coach, team):
    assert create(client, coach, team, name="n" * 50, description="d" * 100).status_code == 201
    assert create(client, coach, team, name="n" * 51).status_code == 422
    assert create(client, coach, team, description="d" * 101).status_code == 422
    assert create(client, coach, team, name="   ").status_code == 422


def test_the_limit_counts_what_is_saved_not_the_spaces_around(client, coach, team):
    play = create(client, coach, team, name="  " + "n" * 50 + "  ", description="  dos   espacios  ").json()
    assert play["name"] == "n" * 50 and play["description"] == "dos espacios"


def test_editing_a_play_respects_the_same_limits(client, coach, team):
    play = create(client, coach, team).json()
    url = f"/api/tactical-plays/{play['id']}"
    assert client.put(url, headers=coach["headers"], json={"name": "n" * 51}).status_code == 422
    assert client.put(url, headers=coach["headers"], json={"description": "d" * 101}).status_code == 422
    changed = client.put(url, headers=coach["headers"], json={"name": "Presión tras pérdida", "description": ""}).json()
    assert changed["name"] == "Presión tras pérdida" and changed["description"] is None


def test_the_coach_writes_his_own_action_type_and_it_is_saved(client, coach, analyst, team):
    created = client.post(f"/api/teams/{team['id']}/action-types", headers=coach["headers"],
                          json={"name": "  Saque de   banda largo "})
    assert created.status_code == 201 and created.json()["name"] == "Saque de banda largo"
    assert [t["name"] for t in types(client, analyst, team)] == ["Saque de banda largo"]   # the staff sees it too
    play = create(client, coach, team, action_type="Saque de banda largo").json()
    assert play["action_type"] == "Saque de banda largo"


def test_the_same_type_is_not_saved_twice(client, coach, team):
    url = f"/api/teams/{team['id']}/action-types"
    first = client.post(url, headers=coach["headers"], json={"name": "Córner corto"})
    again = client.post(url, headers=coach["headers"], json={"name": "CÓRNER CORTO"})
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    assert len(types(client, coach, team)) == 1


def test_action_type_names_have_2_to_40_characters(client, coach, team):
    url = f"/api/teams/{team['id']}/action-types"
    assert client.post(url, headers=coach["headers"], json={"name": "x"}).status_code == 422
    assert client.post(url, headers=coach["headers"], json={"name": "x" * 41}).status_code == 422
    assert client.post(url, headers=coach["headers"], json={"name": "x" * 40}).status_code == 201
    assert create(client, coach, team, action_type="x" * 41).status_code == 422


def test_deleting_a_type_keeps_the_plays_that_use_it(client, coach, team):
    url = f"/api/teams/{team['id']}/action-types"
    kind = client.post(url, headers=coach["headers"], json={"name": "Tiro libre"}).json()
    play = create(client, coach, team, action_type="Tiro libre").json()
    assert client.delete(f"{url}/{kind['id']}", headers=coach["headers"]).status_code == 204
    assert types(client, coach, team) == []
    assert client.get(f"/api/tactical-plays/{play['id']}", headers=coach["headers"]).json()["action_type"] == "Tiro libre"
    assert client.delete(f"{url}/{kind['id']}", headers=coach["headers"]).status_code == 404


def test_only_the_coach_writes_types_and_other_teams_never_see_them(client, coach, analyst, team):
    url = f"/api/teams/{team['id']}/action-types"
    client.post(url, headers=coach["headers"], json={"name": "Tiro libre"})
    assert client.post(url, headers=analyst["headers"], json={"name": "Otra"}).status_code == 403
    outsider = register(client, "otro@club.com", "COACH")
    other = client.post("/api/teams", headers=outsider["headers"], json={"name": "Otro club"}).json()
    assert client.get(url, headers=outsider["headers"]).status_code in (403, 404)
    assert types(client, outsider, other) == []
