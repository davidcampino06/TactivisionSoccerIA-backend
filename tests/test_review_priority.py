"""Priority queue (binary max-heap) and the review order of the AI's possible issues."""

import random
from datetime import datetime, timedelta

import pytest
from conftest import register

from data_structures import EmptyStructureError, PriorityQueue
from models import AIRecommendation
from services.review_priority import by_priority, review_queue


def is_heap(queue: PriorityQueue) -> bool:
    entries = queue._heap
    return all(not queue._beats(entries[i], entries[(i - 1) // 2]) for i in range(1, len(entries)))


def test_heap_keeps_the_biggest_on_top():
    queue = PriorityQueue(key=lambda value: value)
    values = random.Random(7).sample(range(1000), 200)
    for value in values:
        queue.push(value)
        assert is_heap(queue)
    assert queue.peek() == max(values)
    assert queue.pop_many(len(values)) == sorted(values, reverse=True)
    assert queue.is_empty()


def test_heapify_and_pop_many():
    values = [5, 1, 9, 3, 7, 9, 2]
    queue = PriorityQueue.from_items(values, key=lambda value: value)
    assert is_heap(queue) and len(queue) == 7
    assert queue.as_array()[0] == 9
    assert queue.pop_many(3) == [9, 9, 7]
    assert len(queue) == 4
    assert queue.pop_many(10) == [5, 3, 2, 1]


def test_ties_keep_arrival_order_and_empty_heap_fails():
    queue = PriorityQueue(key=lambda item: item[0])
    for item in [(1, "a"), (2, "b"), (1, "c"), (2, "d")]:
        queue.push(item)
    assert [name for _, name in queue.pop_many(4)] == ["b", "d", "a", "c"]
    with pytest.raises(EmptyStructureError):
        queue.pop()
    with pytest.raises(EmptyStructureError):
        PriorityQueue(key=len).peek()


def rec(title, severity, confidence, status="GENERATED", minutes=0):
    return AIRecommendation(id=title, title=title, severity=severity, confidence=confidence, status=status,
                            created_at=datetime(2026, 10, 1) + timedelta(minutes=minutes))


def test_review_order_severity_then_unreviewed_then_confidence():
    items = [
        rec("low-sure", "LOW", 0.99),
        rec("high-reviewed", "HIGH", 0.95, status="REVIEWED"),
        rec("high-new", "HIGH", 0.60),
        rec("medium", "MEDIUM", 0.90),
        rec("high-new-sure", "HIGH", 0.80),
        rec("closed", "HIGH", 0.99, status="CONFIRMED"),
    ]
    assert [item.title for item in by_priority(items)][:3] == ["high-new-sure", "high-new", "closed"]
    top, heap, total = review_queue(items, limit=3)
    assert [item.title for item in top] == ["high-new-sure", "high-new", "high-reviewed"]
    assert total == 5 and len(heap) == 5 and heap[0].title == "high-new-sure"


@pytest.fixture
def issues(client, coach, team, monkeypatch):
    from services import ai_client
    from test_video_analysis import FakeClient, FakeRealFactory, fake_payload
    monkeypatch.setitem(ai_client._FACTORIES, "REAL_VIDEO_ANALYSIS", FakeRealFactory)
    FakeClient.response = fake_payload()
    h = coach["headers"]
    match = client.post(f"/api/teams/{team['id']}/matches", headers=h,
                        json={"opponent": "Nacional", "match_date": "2026-09-01T15:00:00"}).json()
    video = client.post(f"/api/matches/{match['id']}/videos", headers=h,
                        files={"video": ("clip.mp4", b"fake-bytes", "video/mp4")}).json()
    analysis = client.post(f"/api/videos/{video['id']}/analysis", headers=h, json={}).json()
    return {"match": match, "analysis": analysis}


def test_team_review_queue(client, coach, team, issues):
    h = coach["headers"]
    queue = client.get(f"/api/teams/{team['id']}/review-queue?limit=3", headers=h).json()
    assert queue["total"] >= 1 and queue["items"][0]["rank"] == 1
    first = queue["items"][0]
    assert first["opponent"] == "Nacional" and first["analysis_id"] == issues["analysis"]["id"]
    assert queue["heap"][0]["id"] == first["id"]

    # A confirmed issue leaves the queue.
    client.patch(f"/api/recommendations/{first['id']}", headers=h, json={"action": "confirm"})
    after = client.get(f"/api/teams/{team['id']}/review-queue", headers=h).json()
    assert first["id"] not in [item["id"] for item in after["items"]]
    assert after["total"] == queue["total"] - 1


def test_review_queue_is_private(client, team, issues):
    outsider = register(client, "coach.b@club.com", "COACH")["headers"]
    response = client.get(f"/api/teams/{team['id']}/review-queue", headers=outsider)
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
