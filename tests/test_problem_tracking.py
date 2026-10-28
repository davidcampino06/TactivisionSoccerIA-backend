"""Follow-up of the confirmed problems across the matches analysed after the confirmation."""

import database
import rls
from models import TacticalIndicator
from test_review_inbox import analyse, with_own_team
from test_video_analysis import fake_ai, fake_payload  # noqa: F401  (fixtures)

PROBLEM = "Possible tactical issue: excessive distance between defensive and midfield lines"


def without_problem(measured: bool = True, samples: int | None = 40):
    """The line distance judged in ``samples`` frames, below its threshold: the AI raises nothing."""
    payload = fake_payload()
    payload["recommendations"], payload["possible_issues"] = [], []
    payload.setdefault("teams", {})["own_team"] = "TEAM_A"  # the kit colour told which team is ours
    for indicator in payload["tactical_indicators"]:
        indicator.update(samples=samples, exceed_ratio=0.2 if samples is not None else None)
    if not measured:  # e.g. no attack direction: the line distance cannot be measured
        payload["tactical_indicators"] = [i for i in payload["tactical_indicators"]
                                          if i["name"] != "team_a.defensive_midfield_distance"]
    return payload


def tracking(client, coach, team):
    response = client.get(f"/api/teams/{team['id']}/problem-tracking", headers=coach["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def confirm_first_problem(client, coach, team):
    inbox = client.get(f"/api/teams/{team['id']}/review-inbox", headers=coach["headers"]).json()
    client.patch(f"/api/recommendations/{inbox['problems'][0]['id']}", headers=coach["headers"], json={"action": "confirm"})


def test_only_confirmed_problems_are_followed(client, coach, team, fake_ai):
    analyse(client, coach["headers"], team, "Nacional", "2026-09-01T15:00:00", fake_payload())
    assert tracking(client, coach, team) == []
    confirm_first_problem(client, coach, team)
    [item] = tracking(client, coach, team)
    assert item["title"] == PROBLEM.capitalize() and item["trend"] == "NO_DATA"
    assert [step["state"] for step in item["timeline"]] == ["CONFIRMED"]


def test_states_after_the_confirmation_say_what_each_analysis_shows(client, coach, team, fake_ai):
    analyse(client, coach["headers"], team, "Nacional", "2026-09-01T15:00:00", fake_payload())
    confirm_first_problem(client, coach, team)
    analyse(client, coach["headers"], team, "Medellín", "2026-09-08T15:00:00", without_problem())
    analyse(client, coach["headers"], team, "Junior", "2026-09-15T15:00:00", without_problem(measured=False))
    [item] = tracking(client, coach, team)
    assert [(s["opponent"], s["state"]) for s in item["timeline"]] == [
        ("Nacional", "CONFIRMED"), ("Medellín", "NOT_DETECTED"), ("Junior", "NOT_MEASURED")]
    assert (item["trend"], item["measured_after"], item["came_back"]) == ("GONE", 1, 0)

    analyse(client, coach["headers"], team, "Cali", "2026-09-22T15:00:00", fake_payload())
    [item] = tracking(client, coach, team)
    assert item["timeline"][-1]["state"] == "DETECTED"
    assert (item["trend"], item["measured_after"], item["came_back"]) == ("RECURRING", 2, 1)

    analyse(client, coach["headers"], team, "Pasto", "2026-09-29T15:00:00", without_problem())
    assert tracking(client, coach, team)[0]["trend"] == "IMPROVING"


def test_too_few_frames_or_an_older_analysis_cannot_say_it_did_not_appear(client, coach, team, fake_ai):
    analyse(client, coach["headers"], team, "Nacional", "2026-09-01T15:00:00", fake_payload())
    confirm_first_problem(client, coach, team)
    analyse(client, coach["headers"], team, "Medellín", "2026-09-08T15:00:00", without_problem(samples=3))
    analyse(client, coach["headers"], team, "Junior", "2026-09-15T15:00:00", without_problem(samples=None))
    [item] = tracking(client, coach, team)
    assert [s["state"] for s in item["timeline"]] == ["CONFIRMED", "NOT_MEASURED", "NOT_MEASURED"]
    assert item["trend"] == "NO_DATA"


def test_without_knowing_our_team_both_teams_must_have_been_judged(client, coach, team, fake_ai):
    analyse(client, coach["headers"], team, "Nacional", "2026-09-01T15:00:00", fake_payload())
    confirm_first_problem(client, coach, team)
    payload = without_problem()
    del payload["teams"]["own_team"]
    payload["tactical_indicators"].append({"name": "team_b.defensive_midfield_distance", "value": 0.1,
                                           "unit": "frame_width_ratio", "threshold": 0.169, "samples": 3, "exceed_ratio": 0.0})
    analyse(client, coach["headers"], team, "Medellín", "2026-09-08T15:00:00", payload)
    [item] = tracking(client, coach, team)
    assert item["timeline"][-1]["state"] == "NOT_MEASURED"  # Equipo B could be ours and had only 3 frames


def test_the_frames_judged_are_stored_with_each_indicator(client, coach, team, fake_ai):
    _, analysis_id = analyse(client, coach["headers"], team, "Medellín", "2026-09-08T15:00:00", without_problem(samples=12))
    with rls.mark_system(database.SessionLocal()) as db:
        rows = db.query(TacticalIndicator).filter(TacticalIndicator.video_analysis_id == analysis_id).all()
    assert rows and {(r.samples, r.exceed_ratio) for r in rows} == {(12, 0.2)}


def test_matches_before_the_first_confirmation_and_the_rival_do_not_count(client, coach, team, fake_ai):
    analyse(client, coach["headers"], team, "Envigado", "2026-08-25T15:00:00", without_problem())
    analyse(client, coach["headers"], team, "Nacional", "2026-09-01T15:00:00", fake_payload())
    confirm_first_problem(client, coach, team)
    analyse(client, coach["headers"], team, "Medellín", "2026-09-08T15:00:00", with_own_team("TEAM_B"))
    [item] = tracking(client, coach, team)
    # Envigado is before the confirmation; in Medellín the problem is of TEAM_A, the rival there.
    assert [(s["opponent"], s["state"]) for s in item["timeline"]] == [("Nacional", "CONFIRMED"), ("Medellín", "NOT_MEASURED")]


def test_the_match_plan_shows_the_follow_up_up_to_its_date(client, coach, team, fake_ai):
    analyse(client, coach["headers"], team, "Nacional", "2026-09-01T15:00:00", fake_payload())
    confirm_first_problem(client, coach, team)
    analyse(client, coach["headers"], team, "Medellín", "2026-09-08T15:00:00", without_problem())
    upcoming = client.post(f"/api/teams/{team['id']}/matches", headers=coach["headers"],
                           json={"opponent": "Tolima", "match_date": "2026-09-12T15:00:00"}).json()
    analyse(client, coach["headers"], team, "Cali", "2026-09-22T15:00:00", fake_payload())  # after the plan's match
    plan = client.get(f"/api/matches/{upcoming['id']}/plan", headers=coach["headers"]).json()
    [item] = plan["to_correct"]
    assert item["tracking"]["trend"] == "GONE" and len(item["tracking"]["timeline"]) == 2
    pdf = client.get(f"/api/matches/{upcoming['id']}/plan.pdf", headers=coach["headers"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
