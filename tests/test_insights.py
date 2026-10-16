"""Comparison and evolution: risk direction, threshold status and trend assessment."""

import pytest

from services.match_timeline import assess_trend, risk_direction, threshold_status


def test_risk_direction_matches_the_ai_rules():
    assert risk_direction("team_a.defensive_midfield_distance") == "above"
    assert risk_direction("team_b.team_width") == "below"
    assert risk_direction("team_a.defensive_line_position") == "below"
    assert risk_direction("max_zone_numerical_difference") == "above"
    # Possession phase indicators (AI 0.6): too few pressers, too narrow, nobody ahead of the ball.
    for name in ("team_b.pressure_on_ball", "team_a.attacking_width", "team_a.players_ahead_of_ball"):
        assert risk_direction(name) == "below"
    assert threshold_status("team_b.pressure_on_ball", 0.2, 0.5) == "EXCEEDS"
    assert threshold_status("team_a.attacking_width", 0.5, 0.35) == "OK"


@pytest.mark.parametrize("name, value, threshold, expected", [
    ("team_a.defensive_midfield_distance", 0.30, 0.22, "EXCEEDS"),
    ("team_a.defensive_midfield_distance", 0.22, 0.22, "EXCEEDS"),  # same >= rule as the AI service
    ("team_a.defensive_midfield_distance", 0.10, 0.22, "OK"),
    ("team_a.team_width", 0.25, 0.30, "EXCEEDS"),
    ("team_a.team_width", 0.45, 0.30, "OK"),
    ("team_a.team_width", None, 0.30, None),
    ("ball_position_x", 0.5, None, None),
])
def test_threshold_status(name, value, threshold, expected):
    assert threshold_status(name, value, threshold) == expected


@pytest.mark.parametrize("name, trend, expected", [
    ("team_a.defensive_midfield_distance", "DECREASING", "IMPROVING"),
    ("team_a.defensive_midfield_distance", "INCREASING", "WORSENING"),
    ("team_a.team_width", "INCREASING", "IMPROVING"),
    ("team_a.team_width", "DECREASING", "WORSENING"),
    ("team_a.team_width", "STABLE", "STABLE"),
    ("team_a.team_width", "INSUFFICIENT_DATA", "INSUFFICIENT_DATA"),
])
def test_trend_assessment(name, trend, expected):
    assert assess_trend(name, trend, 0.3) == expected


def test_no_threshold_means_no_assessment():
    assert assess_trend("ball_position_x", "INCREASING", None) is None
