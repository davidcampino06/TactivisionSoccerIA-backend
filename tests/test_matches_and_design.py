def test_match_result_events_and_neighbors(client, coach, team, match):
    headers = coach["headers"]
    result = client.put(f"/api/matches/{match['id']}/result", headers=headers, json={"home_score": 2, "away_score": 1}).json()
    assert result["result"] == "WIN" and result["status"] == "PLAYED"
    event = client.post(f"/api/matches/{match['id']}/events", headers=headers,
                        json={"minute": 12, "event_type": "SHOT", "zone": "BOX", "source_x": 90, "source_y": 30})
    assert event.status_code == 201
    later = client.post(f"/api/teams/{team['id']}/matches", headers=headers,
                        json={"opponent": "Medellin", "match_date": "2026-09-08T15:00:00"}).json()
    neighbors = client.get(f"/api/matches/{later['id']}/neighbors", headers=headers).json()
    assert neighbors["previous"]["id"] == match["id"] and neighbors["next"] is None


def test_formations_validation_and_link(client, coach, match):
    headers = coach["headers"]
    assert client.post("/api/formations", headers=headers, json={"name": "4-4-3"}).status_code == 422
    formation = client.post("/api/formations", headers=headers, json={"name": "4-3-3"}).json()
    assert client.post(f"/api/matches/{match['id']}/formations", headers=headers,
                       json={"formation_id": formation["id"]}).status_code == 204
    assert client.get(f"/api/matches/{match['id']}/formations", headers=headers).json()[0]["name"] == "4-3-3"


def test_tactical_versions_prototype_and_undo(client, coach, team, match):
    headers = coach["headers"]
    play = client.post(f"/api/teams/{team['id']}/tactical-plays", headers=headers, json={
        "name": "High press", "action_type": "PRESSING",
        "configuration": {"formation": "4-3-3", "lines": {"defense": 40, "midfield": 55}}}).json()
    v2 = client.post(f"/api/tactical-plays/{play['id']}/versions", headers=headers,
                     json={"configuration": {"lines": {"defense": 48}}}).json()
    assert v2["version_number"] == 2 and v2["is_current"]
    assert v2["configuration"] == {"formation": "4-3-3", "lines": {"defense": 48, "midfield": 55}}

    versions = client.get(f"/api/tactical-plays/{play['id']}/versions", headers=headers).json()
    assert versions[0]["configuration"]["lines"]["defense"] == 40  # original untouched (prototype clone)

    undone = client.post(f"/api/tactical-plays/{play['id']}/versions/undo", headers=headers).json()
    assert undone["version_number"] == 1 and undone["is_current"]
    assert client.post(f"/api/tactical-plays/{play['id']}/versions/undo", headers=headers).status_code == 409

    assert client.post(f"/api/matches/{match['id']}/tactical-plays", headers=headers,
                       json={"tactical_play_id": play["id"]}).status_code == 204


BOARD = {
    "schema": 1, "formation": "4-3-3", "notes": "Presión tras pérdida",
    "tokens": [{"id": "o1", "side": "own", "x": 5, "y": 34, "label": "1", "player_id": None}],
    "arrows": [{"id": "a1", "kind": "pass", "x1": 5, "y1": 34, "x2": 30, "y2": 20}],
}


def test_play_list_shows_current_version(client, coach, team, analyst):
    h = coach["headers"]
    first = client.post(f"/api/teams/{team['id']}/tactical-plays", headers=h,
                        json={"name": "Salida", "action_type": "BUILD_UP", "configuration": BOARD}).json()
    second = client.post(f"/api/teams/{team['id']}/tactical-plays", headers=h,
                         json={"name": "Presión", "action_type": "PRESSING", "configuration": {}}).json()
    moved = {**BOARD, "tokens": [{**BOARD["tokens"][0], "x": 12}]}
    client.post(f"/api/tactical-plays/{first['id']}/versions", headers=h, json={"configuration": moved})

    plays = client.get(f"/api/teams/{team['id']}/tactical-plays", headers=analyst["headers"]).json()
    assert [p["id"] for p in plays] == [first["id"], second["id"]]  # most recently edited first
    assert plays[0]["version_count"] == 2 and plays[0]["current_version_number"] == 2
    assert plays[0]["configuration"]["tokens"][0]["x"] == 12
    assert plays[1]["configuration"] == {}


def test_full_board_replaces_arrays(client, coach, team):
    """The editor sends the whole board: lists (tokens, arrows) are replaced, not merged."""
    h = coach["headers"]
    play = client.post(f"/api/teams/{team['id']}/tactical-plays", headers=h,
                       json={"name": "Contra", "configuration": BOARD}).json()
    emptied = client.post(f"/api/tactical-plays/{play['id']}/versions", headers=h,
                          json={"configuration": {**BOARD, "arrows": []}}).json()
    assert emptied["configuration"]["arrows"] == [] and emptied["configuration"]["notes"] == BOARD["notes"]


def test_rename_play_and_roles(client, coach, team, analyst):
    play = client.post(f"/api/teams/{team['id']}/tactical-plays", headers=coach["headers"], json={"name": "A"}).json()
    renamed = client.put(f"/api/tactical-plays/{play['id']}", headers=coach["headers"],
                         json={"name": "Balón parado ofensivo", "action_type": "SET_PIECE"})
    assert renamed.json()["name"] == "Balón parado ofensivo" and renamed.json()["action_type"] == "SET_PIECE"
    denied = client.put(f"/api/tactical-plays/{play['id']}", headers=analyst["headers"], json={"name": "X"})
    assert denied.status_code == 403
    saved = client.post(f"/api/tactical-plays/{play['id']}/versions", headers=analyst["headers"], json={"configuration": {}})
    assert saved.status_code == 403


def test_configuration_size_is_limited(client, coach, team):
    huge = {"notes": "x" * 70_000}
    response = client.post(f"/api/teams/{team['id']}/tactical-plays", headers=coach["headers"],
                           json={"name": "Enorme", "configuration": huge})
    assert response.status_code == 422


def test_link_and_unlink_play_from_match(client, coach, team, match, analyst):
    h = coach["headers"]
    play = client.post(f"/api/teams/{team['id']}/tactical-plays", headers=h, json={"name": "Córner"}).json()
    assert client.post(f"/api/matches/{match['id']}/tactical-plays", headers=analyst["headers"],
                       json={"tactical_play_id": play["id"]}).status_code == 204
    linked = client.get(f"/api/tactical-plays/{play['id']}/matches", headers=analyst["headers"]).json()
    assert [m["id"] for m in linked] == [match["id"]]
    assert client.delete(f"/api/matches/{match['id']}/tactical-plays/{play['id']}", headers=h).status_code == 204
    assert client.get(f"/api/tactical-plays/{play['id']}/matches", headers=h).json() == []
    again = client.delete(f"/api/matches/{match['id']}/tactical-plays/{play['id']}", headers=h)
    assert again.status_code == 404 and again.json()["code"] == "NOT_FOUND"
