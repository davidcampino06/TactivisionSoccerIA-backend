"""Which possible issue should the coach look at first.

The AI can raise several possible issues per match. They are put in a PriorityQueue (binary
max-heap, data_structures.py) ordered by:

    1. severity      HIGH > MEDIUM > LOW
    2. not reviewed  an issue nobody has opened yet goes before one already reviewed
    3. confidence    how sure the AI is (0-1)
    4. newest first  for the same values, the most recent analysis wins

Confirmed and dismissed issues are closed: they are not part of the review queue.
"""

from __future__ import annotations

from collections.abc import Iterable

from data_structures import PriorityQueue
from models import AIRecommendation, RecommendationStatus

SEVERITY_WEIGHT = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
OPEN_STATES = (RecommendationStatus.GENERATED, RecommendationStatus.REVIEWED)


def review_priority(recommendation: AIRecommendation) -> tuple:
    """Bigger tuple = more urgent."""
    return (
        SEVERITY_WEIGHT.get(recommendation.severity, 0),
        1 if recommendation.status == RecommendationStatus.GENERATED else 0,
        float(recommendation.confidence or 0),
        recommendation.created_at.timestamp() if recommendation.created_at else 0.0,
    )


def by_priority(recommendations: Iterable[AIRecommendation]) -> list[AIRecommendation]:
    """All of them, most urgent first (heapify O(n) + n pops O(n log n): heap sort)."""
    queue = PriorityQueue.from_items(recommendations, key=review_priority)
    return queue.pop_many(len(queue))


def review_queue(recommendations: Iterable[AIRecommendation], limit: int) -> tuple[list[AIRecommendation], list[AIRecommendation], int]:
    """The ``limit`` most urgent open issues, the heap as stored (to draw it) and how many are open.

    Only the first ``limit`` are popped: O(n + k log n) instead of sorting all of them."""
    queue = PriorityQueue.from_items(
        (item for item in recommendations if item.status in OPEN_STATES), key=review_priority)
    total = len(queue)
    heap = queue.as_array()
    return queue.pop_many(limit), heap, total
