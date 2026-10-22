"""Player availability: injured, suspended or unavailable, why, until when, and the bell reminder."""

from datetime import date

import pytest

from services import player_returns

TODAY = date(2026, 10, 21)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(player_returns, "today", lambda: TODAY)


@pytest.fixture
def player(client, coach, team):
    response = client.post(f"/api/teams/{team['id']}/players", headers=coach["headers"],
                           json={"first_name": "Martín", "last_name": "Agudelo", "shirt_number": 12})
    assert response.status_code == 201, response.text
    return response.json()


def put(client, coach, player, **body):
    response = client.put(f"/api/players/{player['id']}", headers=coach["headers"], json=body)
    assert response.status_code == 200, response.text
    return response.json()


def returns(client, headers):
    return [item for item in client.get("/api/notifications", headers=headers).json()
            if item["event"] == "PLAYER_RETURN_DUE"]


def test_injury_with_reason_and_return_date(client, coach, player):
    injured = put(client, coach, player, status="INJURED", availability_note="  Esguince de tobillo  ",
                  expected_return="2026-10-30")
    assert (injured["status"], injured["availability_note"], injured["expected_return"]) == (
        "INJURED", "Esguince de tobillo", "2026-10-30")
    assert client.get(f"/api/players/{player['id']}", headers=coach["headers"]).json()["availability_note"] == \
        "Esguince de tobillo"


def test_personal_reasons_are_a_status_of_their_own(client, coach, player):
    away = put(client, coach, player, status="UNAVAILABLE", availability_note="Viaje familiar")
    assert (away["status"], away["availability_note"], away["expected_return"]) == ("UNAVAILABLE", "Viaje familiar", None)
    assert put(client, coach, player, availability_note="   ")["availability_note"] is None  # blank = no reason


def test_back_to_active_clears_the_reason_and_the_date(client, coach, player):
    put(client, coach, player, status="SUSPENDED", availability_note="Doble amarilla", expected_return="2026-11-01")
    active = put(client, coach, player, status="ACTIVE")
    assert (active["availability_note"], active["expected_return"]) == (None, None)
    # An available player has no absence to explain: a reason sent alone is not kept.
    assert put(client, coach, player, availability_note="Nada")["availability_note"] is None


def test_removing_the_player_clears_the_absence(client, coach, player):
    put(client, coach, player, status="INJURED", availability_note="Rotura de ligamentos", expected_return="2027-03-01")
    removed = client.request("DELETE", f"/api/players/{player['id']}", headers=coach["headers"],
                             json={"withdrawal_reason": "Fin de contrato"}).json()
    assert (removed["status"], removed["availability_note"], removed["expected_return"]) == ("INACTIVE", None, None)


def test_unknown_status_is_rejected(client, coach, player):
    response = client.put(f"/api/players/{player['id']}", headers=coach["headers"], json={"status": "ON_HOLIDAY"})
    assert response.status_code == 422


def test_the_bell_reminds_the_return_day_once_for_the_whole_team(client, coach, analyst, player):
    put(client, coach, player, status="INJURED", availability_note="Esguince de tobillo", expected_return="2026-10-21")

    reminders = returns(client, coach["headers"])
    assert len(reminders) == 1 and not reminders[0]["read"]
    assert reminders[0]["message"] == ("Hoy es la fecha estimada de regreso de #12 Martín Agudelo (lesionado: Esguince "
                                       "de tobillo). Revisa si ya puede jugar y actualiza su estado.")
    assert len(returns(client, analyst["headers"])) == 1                   # the analyst sees the same one
    client.get("/api/notifications/unread-count", headers=coach["headers"])
    assert len(returns(client, coach["headers"])) == 1                     # polling again never repeats it
    # Nothing changes by itself: the coach decides whether he is back.
    assert client.get(f"/api/players/{player['id']}", headers=coach["headers"]).json()["status"] == "INJURED"


def test_future_returns_wait_and_a_new_date_is_reminded_again(client, coach, player):
    put(client, coach, player, status="SUSPENDED", expected_return="2026-10-25")
    assert returns(client, coach["headers"]) == []

    put(client, coach, player, expected_return="2026-10-19")              # the date was in fact earlier
    assert returns(client, coach["headers"])[0]["message"].startswith(
        "El 19/10/2026 era la fecha estimada de regreso de #12 Martín Agudelo (suspendido).")

    put(client, coach, player, expected_return="2026-10-21")              # postponed: reminded on the new day
    assert len(returns(client, coach["headers"])) == 2


def test_available_players_are_never_reminded(client, coach, player):
    put(client, coach, player, status="INJURED", expected_return="2026-10-21")
    put(client, coach, player, status="ACTIVE")
    put(client, coach, player, status="UNAVAILABLE")
    assert returns(client, coach["headers"]) == []


def test_unread_count_includes_the_reminder(client, coach, player):
    before = client.get("/api/notifications/unread-count", headers=coach["headers"]).json()["unread"]
    put(client, coach, player, status="UNAVAILABLE", availability_note="Motivo personal", expected_return="2026-10-20")
    assert client.get("/api/notifications/unread-count", headers=coach["headers"]).json()["unread"] == before + 1
