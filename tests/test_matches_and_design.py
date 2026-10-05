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
