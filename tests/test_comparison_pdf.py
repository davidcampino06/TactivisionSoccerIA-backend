"""Downloading the comparison of the chosen matches, with the charts of the differences."""

from conftest import register
from services.comparison_pdf import comparison_blocks
from services.match_timeline import change_assessment, change_percent
from test_clip_library import analyse, new_match, upload
from test_video_analysis import FakeClient, fake_ai, fake_payload  # noqa: F401  (fixtures)


def two_analysed_matches(client, coach, team):
    ids = []
    for opponent, date, width in (("Nacional", "2026-09-01T15:00:00", 0.40), ("Medellín", "2026-09-08T15:00:00", 0.50)):
        match = new_match(client, coach, team, opponent, date)
        payload = fake_payload()
        for indicator in payload["tactical_indicators"]:
            if indicator["name"] == "team_a.team_width":
                indicator["value"] = width
        analyse(client, coach, upload(client, coach, match), payload)
        ids.append(match["id"])
    return ids


def query(ids):
    return "&".join(f"match_ids={i}" for i in ids)


def test_the_change_between_first_and_last_is_a_percentage_of_the_first():
    assert change_percent(0.40, 0.50) == 25.0 and change_percent(0.50, 0.40) == -20.0
    assert change_percent(0, 3) is None and change_percent(None, 3) is None and change_percent(2, None) is None


def test_a_change_is_better_when_it_moves_away_from_the_risky_side():
    # A narrow team is the risk: getting wider is better. A big gap between lines is the risk: bigger is worse.
    assert change_assessment("team_a.team_width", 0.40, 0.50) == "BETTER"
    assert change_assessment("team_a.team_width", 0.50, 0.40) == "WORSE"
    assert change_assessment("team_a.largest_line_gap", 0.20, 0.30) == "WORSE"
    assert change_assessment("team_a.largest_line_gap", 0.200, 0.201) == "SAME"
    assert change_assessment("team_a.team_width", None, 0.4) is None


def test_the_comparison_says_how_much_each_indicator_changed(client, coach, team, fake_ai):
    ids = two_analysed_matches(client, coach, team)
    data = client.get(f"/api/teams/{team['id']}/comparisons?{query(ids)}", headers=coach["headers"]).json()
    width = next(row for row in data["indicators"] if row["indicator"] == "team_a.team_width")
    assert width["values"] == [0.4, 0.5] and width["change_percent"] == 25.0 and width["change_assessment"] == "BETTER"


def test_the_comparison_of_the_chosen_matches_downloads_as_a_pdf(client, coach, analyst, team, fake_ai):
    ids = two_analysed_matches(client, coach, team)
    response = client.get(f"/api/teams/{team['id']}/comparisons/pdf?{query(ids)}", headers=analyst["headers"])
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert "comparacion-de-partidos.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF") and len(response.content) > 2500


def test_the_pdf_draws_the_differences_and_one_chart_per_indicator(client, coach, team, fake_ai):
    ids = two_analysed_matches(client, coach, team)
    data = client.get(f"/api/teams/{team['id']}/comparisons?{query(ids)}", headers=coach["headers"]).json()
    blocks = comparison_blocks(data)
    changes = [block for block in blocks if block["kind"] == "changes"]
    bars = [block for block in blocks if block["kind"] == "bars"]
    assert changes and all(len(block["bars"]) == 2 for block in bars)
    assert len(bars) == len([row for row in data["indicators"] if any(v is not None for v in row["values"])])
    width = next(row for block in changes for row in block["rows"] if row["label"] == "Ancho del equipo")
    assert width["percent"] == 25.0 and width["assessment"] == "BETTER" and width["text"] == "+25 %"
    legend = next(block for block in blocks if block["kind"] == "legend")
    assert [title.split(" · ")[0] for title, _ in legend["items"]] == ["vs Nacional", "vs Medellín"]
    chart = next(block for block in bars if block["title"] == "Ancho del equipo")
    assert [bar["text"] for bar in chart["bars"]] == ["40 %", "50 %"] and "mejora" in chart["difference"]


def test_the_pdf_needs_two_matches_and_is_private(client, coach, team, fake_ai):
    ids = two_analysed_matches(client, coach, team)
    one = client.get(f"/api/teams/{team['id']}/comparisons/pdf?match_ids={ids[0]}", headers=coach["headers"])
    assert one.status_code == 400 and one.json()["code"] == "COMPARE_MIN_MATCHES"
    outsider = register(client, "otro@club.com", "COACH")
    client.post("/api/teams", headers=outsider["headers"], json={"name": "Otro club"})
    assert client.get(f"/api/teams/{team['id']}/comparisons/pdf?{query(ids)}", headers=outsider["headers"]).status_code in (403, 404)
