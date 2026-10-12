"""Notifications (the bell): stored per team, read state per user, isolated between teams."""

import pytest
from conftest import register
from test_video_analysis import FakeClient, FakeRealFactory, fake_payload

from services import ai_client
from services.analysis_events import (
    ANALYSIS_STARTED, TACTICAL_ALERT, AnalysisEvent, NotificationCenter, PersistentNotificationObserver,
)
from singleton import SingletonMeta


@pytest.fixture
def analysed(client, coach, team, analyst, monkeypatch):
    """Team with an analyst and one completed real analysis (it raises a HIGH alert)."""
    monkeypatch.setitem(ai_client._FACTORIES, "REAL_VIDEO_ANALYSIS", FakeRealFactory)
    FakeClient.response = fake_payload()
    h = coach["headers"]
    match = client.post(f"/api/teams/{team['id']}/matches", headers=h,
                        json={"opponent": "Nacional", "match_date": "2026-09-01T15:00:00"}).json()
    video = client.post(f"/api/matches/{match['id']}/videos", headers=h,
                        files={"video": ("clip.mp4", b"fake-bytes", "video/mp4")}).json()
    analysis = client.post(f"/api/videos/{video['id']}/analysis", headers=h, json={}).json()
    return {"match": match["id"], "analysis": analysis["id"]}


def unread(client, headers) -> int:
    return client.get("/api/notifications/unread-count", headers=headers).json()["unread"]


def test_analysis_events_are_stored_with_their_match(client, coach, analysed):
    items = client.get("/api/notifications", headers=coach["headers"]).json()
    by_event = {item["event"]: item for item in items}
    assert {"ANALYSIS_COMPLETED", "TACTICAL_ALERT", "ANALYST_JOINED"} <= set(by_event)
    assert "ANALYSIS_STARTED" not in by_event  # only logged
    completed = by_event["ANALYSIS_COMPLETED"]
    assert (completed["analysis_id"], completed["match_id"], completed["read"]) == (
        analysed["analysis"], analysed["match"], False)
    assert items == sorted(items, key=lambda item: item["created_at"], reverse=True)


def test_read_state_is_personal(client, coach, analyst, analysed):
    coach_h, analyst_h = coach["headers"], analyst["headers"]
    total = len(client.get("/api/notifications", headers=coach_h).json())
    assert unread(client, coach_h) == total
    # The analyst caused "joined", so it is already read for him.
    assert unread(client, analyst_h) == total - 1

    first = client.get("/api/notifications", headers=coach_h).json()[0]
    assert client.post(f"/api/notifications/{first['id']}/read", headers=coach_h).status_code == 204
    assert client.post(f"/api/notifications/{first['id']}/read", headers=coach_h).status_code == 204  # idempotent
    assert unread(client, coach_h) == total - 1
    assert unread(client, analyst_h) == total - 1  # unchanged for the analyst

    only_unread = client.get("/api/notifications?unread_only=true", headers=coach_h).json()
    assert first["id"] not in [item["id"] for item in only_unread]
    assert client.post("/api/notifications/read-all", headers=coach_h).json() == {"marked": total - 1}
    assert unread(client, coach_h) == 0
    assert all(item["read"] for item in client.get("/api/notifications", headers=coach_h).json())


def test_other_teams_cannot_see_or_mark(client, coach, analysed):
    first = client.get("/api/notifications", headers=coach["headers"]).json()[0]
    outsider = register(client, "coach.b@club.com", "COACH")["headers"]
    client.post("/api/teams", headers=outsider, json={"name": "Deportivo Sur"})
    assert client.get("/api/notifications", headers=outsider).json() == []
    assert unread(client, outsider) == 0
    marked = client.post(f"/api/notifications/{first['id']}/read", headers=outsider)
    assert (marked.status_code, marked.json()["code"]) == (404, "NOT_FOUND")


def test_administrator_has_no_notifications(client, admin, analysed):
    assert client.get("/api/notifications", headers=admin["headers"]).json() == []
    assert unread(client, admin["headers"]) == 0


def test_notifications_survive_a_restart(client, coach, analysed):
    before = client.get("/api/notifications", headers=coach["headers"]).json()
    SingletonMeta.reset(NotificationCenter)  # a new process would build a new center
    assert client.get("/api/notifications", headers=coach["headers"]).json() == before


def test_only_the_newest_are_kept(client, coach, team):
    observer = PersistentNotificationObserver()
    observer.update(AnalysisEvent(ANALYSIS_STARTED, team["id"], None, "not stored"))
    for number in range(PersistentNotificationObserver.KEEP_PER_TEAM + 5):
        observer.update(AnalysisEvent(TACTICAL_ALERT, team["id"], None, f"alert {number}"))
    items = client.get("/api/notifications?limit=100", headers=coach["headers"]).json()
    assert len(items) == PersistentNotificationObserver.KEEP_PER_TEAM
    assert {item["event"] for item in items} == {TACTICAL_ALERT}
    assert unread(client, coach["headers"]) == PersistentNotificationObserver.KEEP_PER_TEAM
