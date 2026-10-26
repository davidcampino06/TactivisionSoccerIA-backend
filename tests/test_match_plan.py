"""The staff's notes on each problem, the review of strengths, and the match plan built only from what
a person confirmed (migration 0018)."""

import pytest
from conftest import register
from test_video_analysis import FakeClient, fake_ai, fake_payload  # noqa: F401  (fixtures)


@pytest.fixture
def season(client, coach, team, analyst):
    """A played match with one analysis (one problem, one strength) and the next match with a play."""
    h = coach["headers"]
    past = client.post(f"/api/teams/{team['id']}/matches", headers=h,
                       json={"opponent": "Nacional", "match_date": "2026-09-01T15:00:00"}).json()
    nxt = client.post(f"/api/teams/{team['id']}/matches", headers=h,
                      json={"opponent": "Medellín", "match_date": "2026-11-08T15:00:00"}).json()
    video = client.post(f"/api/matches/{past['id']}/videos", headers=h,
                        files={"video": ("clip.mp4", b"fake-bytes", "video/mp4")}).json()
    FakeClient.response = fake_payload()
    analysis = client.post(f"/api/videos/{video['id']}/analysis", headers=h, json={}).json()
    result = client.get(f"/api/analyses/{analysis['id']}/result", headers=h).json()
    play = client.post(f"/api/teams/{team['id']}/tactical-plays", headers=h, json={
        "name": "Salida corta", "action_type": "BUILD_UP",
        "configuration": {"formation": "4-3-3", "notes": "El arquero juega corto con el 4."}}).json()
    client.post(f"/api/matches/{nxt['id']}/tactical-plays", headers=h, json={"tactical_play_id": play["id"]})
    players = {}
    for first, number, position in (("Martín", 1, "GOALKEEPER"), ("Juan", 4, "DEFENDER"), ("Tomás", 8, "MIDFIELDER")):
        players[number] = client.post(f"/api/teams/{team['id']}/players", headers=h, json={
            "first_name": first, "last_name": "Pérez", "shirt_number": number, "position": position}).json()
    client.put(f"/api/players/{players[4]['id']}", headers=h,
               json={"status": "INJURED", "availability_note": "Esguince", "expected_return": "2026-11-20"})
    client.put(f"/api/players/{players[8]['id']}", headers=h,
               json={"status": "SUSPENDED", "availability_note": "Roja directa", "expected_return": "2026-11-01"})
    return {"past": past, "next": nxt, "analysis": analysis["id"], "problem": result["recommendations"][0],
            "strength": result["strengths"][0], "play": play}


def plan_of(client, headers, match):
    response = client.get(f"/api/matches/{match['id']}/plan", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------------------------------ notes
def test_the_analyst_writes_a_signed_note_and_the_coach_gets_it(client, coach, analyst, season):
    problem = season["problem"]
    response = client.post(f"/api/recommendations/{problem['id']}/notes", headers=analyst["headers"],
                           json={"text": "  Pasa al perder el balón: el 5 sube y nadie cubre.  "})
    assert response.status_code == 201, response.text
    note = response.json()
    assert (note["text"], note["author_role"]) == ("Pasa al perder el balón: el 5 sube y nadie cubre.", "ANALYST")
    assert note["author_name"]

    shown = client.get(f"/api/analyses/{season['analysis']}/result", headers=coach["headers"]).json()
    assert [n["id"] for n in shown["recommendations"][0]["notes"]] == [note["id"]]

    coach_bell = client.get("/api/notifications", headers=coach["headers"]).json()
    reminder = next(item for item in coach_bell if item["event"] == "RECOMMENDATION_NOTE")
    assert not reminder["read"] and reminder["analysis_id"] == season["analysis"]
    assert "Pasa al perder el balón" in reminder["message"]
    analyst_bell = client.get("/api/notifications", headers=analyst["headers"]).json()
    assert next(item for item in analyst_bell if item["event"] == "RECOMMENDATION_NOTE")["read"]  # his own


def test_notes_are_checked_and_private(client, coach, season):
    problem = season["problem"]
    assert client.post(f"/api/recommendations/{problem['id']}/notes", headers=coach["headers"],
                       json={"text": "   "}).status_code == 422
    outsider = register(client, "otro@club.com", "COACH")
    client.post("/api/teams", headers=outsider["headers"], json={"name": "Otro club"})
    assert client.post(f"/api/recommendations/{problem['id']}/notes", headers=outsider["headers"],
                       json={"text": "Hola"}).status_code == 404


def test_only_the_author_or_the_coach_deletes_a_note(client, coach, analyst, season):
    problem = season["problem"]
    by_coach = client.post(f"/api/recommendations/{problem['id']}/notes", headers=coach["headers"],
                           json={"text": "Lo trabajamos el martes."}).json()
    by_analyst = client.post(f"/api/recommendations/{problem['id']}/notes", headers=analyst["headers"],
                             json={"text": "Se ve en el minuto 12."}).json()
    denied = client.delete(f"/api/recommendation-notes/{by_coach['id']}", headers=analyst["headers"])
    assert denied.status_code == 403 and denied.json()["code"] == "NOTE_NOT_YOURS"
    assert client.delete(f"/api/recommendation-notes/{by_analyst['id']}", headers=coach["headers"]).status_code == 204
    assert client.delete(f"/api/recommendation-notes/{by_coach['id']}", headers=coach["headers"]).status_code == 204
    shown = client.get(f"/api/analyses/{season['analysis']}/result", headers=coach["headers"]).json()
    assert shown["recommendations"][0]["notes"] == []


# ------------------------------------------------------------------------------------- strengths
def test_a_person_confirms_or_dismisses_a_strength_once(client, coach, season):
    url = f"/api/analyses/{season['analysis']}/strengths/{season['strength']['id']}"
    assert season["strength"]["status"] == "GENERATED"
    confirmed = client.patch(url, headers=coach["headers"], json={"action": "confirm"})
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "CONFIRMED"
    again = client.patch(url, headers=coach["headers"], json={"action": "dismiss"})
    assert again.status_code == 409 and again.json()["code"] == "INVALID_STRENGTH_STATE"
    other = client.patch(f"/api/analyses/{season['analysis']}/strengths/missing", headers=coach["headers"],
                         json={"action": "confirm"})
    assert other.status_code == 404


# ------------------------------------------------------------------------------------------- plan
def test_the_plan_lists_the_squad_and_the_plays_as_registered(client, coach, season):
    plan = plan_of(client, coach["headers"], season["next"])
    assert plan["match"]["opponent"] == "Medellín"
    squad = plan["squad"]
    assert squad["available_count"] == 1
    assert [g["label"] for g in squad["groups"]] == ["Porteros"]
    out = {p["shirt_number"]: p for p in squad["unavailable"]}
    assert (out[4]["status"], out[4]["reason"], out[4]["back_before_match"]) == ("INJURED", "Esguince", False)
    assert (out[8]["status"], out[8]["back_before_match"]) == ("SUSPENDED", True)  # back on 1 Nov, match on 8 Nov
    assert plan["plays"] == [{"id": season["play"]["id"], "name": "Salida corta", "action_type": "BUILD_UP",
                              "description": None, "formation": "4-3-3", "notes": "El arquero juega corto con el 4.",
                              "version": 1}]


def test_only_what_a_person_confirmed_reaches_the_plan(client, coach, analyst, season):
    plan = plan_of(client, coach["headers"], season["next"])
    assert (plan["to_correct"], plan["to_keep"]) == ([], [])
    assert plan["left_out"] == {"problems": 1, "strengths": 1}
    assert [m["opponent"] for m in plan["based_on"]] == ["Nacional"]

    problem, strength = season["problem"], season["strength"]
    client.patch(f"/api/recommendations/{problem['id']}", headers=analyst["headers"], json={"action": "confirm"})
    client.post(f"/api/recommendations/{problem['id']}/notes", headers=analyst["headers"],
                json={"text": "El 5 sube y nadie cubre."})
    client.patch(f"/api/analyses/{season['analysis']}/strengths/{strength['id']}", headers=coach["headers"],
                 json={"action": "confirm"})

    plan = plan_of(client, coach["headers"], season["next"])
    assert plan["left_out"] == {"problems": 0, "strengths": 0}
    [item] = plan["to_correct"]
    assert item["severity"] == "HIGH" and [o["opponent"] for o in item["occurrences"]] == ["Nacional"]
    assert [(n["role"], n["text"], n["opponent"]) for n in item["notes"]] == [("analista", "El 5 sube y nadie cubre.", "Nacional")]
    [keep] = plan["to_keep"]
    assert (keep["title"], keep["keep"]) == ("Siempre con un compañero cerca", "Seguir moviéndose como bloque.")


def test_dismissed_items_and_later_matches_never_reach_the_plan(client, coach, season):
    client.patch(f"/api/recommendations/{season['problem']['id']}", headers=coach["headers"], json={"action": "dismiss"})
    plan = plan_of(client, coach["headers"], season["next"])
    assert plan["to_correct"] == [] and plan["left_out"]["problems"] == 0
    # The plan of the analysed match itself only looks at matches played before it: none.
    earlier = plan_of(client, coach["headers"], season["past"])
    assert earlier["based_on"] == [] and earlier["to_keep"] == []


def test_the_plan_downloads_as_pdf(client, coach, season):
    response = client.get(f"/api/matches/{season['next']['id']}/plan.pdf", headers=coach["headers"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="plan-medell-n.pdf"' in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF") and len(response.content) > 1500


def test_the_plan_is_private(client, season):
    outsider = register(client, "otro@club.com", "COACH")
    assert client.get(f"/api/matches/{season['next']['id']}/plan", headers=outsider["headers"]).status_code == 404
