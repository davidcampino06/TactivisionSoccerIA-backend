"""FIFO analysis queue (Queue data structure + Singleton).

Video analysis can take minutes. The HTTP request only enqueues the job and
returns 202; one background worker consumes the queue in arrival order, so the
AI Service (CPU-bound) receives one video at a time.

ANALYSIS_EXECUTION=sync runs jobs inline (used by automated tests).
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from data_structures import EmptyStructureError, Queue
from singleton import SingletonMeta

logger = logging.getLogger("tactivision.queue")


@dataclass(eq=False)
class AnalysisJob:
    analysis_id: str
    options: dict = field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, AnalysisJob) and other.analysis_id == self.analysis_id

    def __hash__(self) -> int:
        return hash(self.analysis_id)


class AnalysisJobQueue(metaclass=SingletonMeta):
    def __init__(self) -> None:
        self._queue: Queue[AnalysisJob] = Queue()
        self._handler: Callable[[AnalysisJob], None] | None = None
        self._worker: threading.Thread | None = None
        self._worker_lock = threading.Lock()
        self.synchronous = os.getenv("ANALYSIS_EXECUTION", "queue").lower() == "sync"

    def set_handler(self, handler: Callable[[AnalysisJob], None]) -> None:
        self._handler = handler

    def submit(self, job: AnalysisJob) -> int:
        """Returns the queue position (0 when executed synchronously)."""
        if self._handler is None:
            raise RuntimeError("AnalysisJobQueue has no handler configured.")
        if self.synchronous:
            self._handler(job)
            return 0
        position = self._queue.enqueue(job)
        self._ensure_worker()
        return position

    def position(self, analysis_id: str) -> int | None:
        return self._queue.position_of(AnalysisJob(analysis_id))

    def discard(self, analysis_id: str) -> bool:
        return self._queue.remove(AnalysisJob(analysis_id))

    def __len__(self) -> int:
        return len(self._queue)

    def _ensure_worker(self) -> None:
        with self._worker_lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._consume, name="analysis-worker", daemon=True)
                self._worker.start()

    def _consume(self) -> None:
        while True:
            try:
                job = self._queue.dequeue(timeout=60)
            except EmptyStructureError:
                continue
            try:
                self._handler(job)
            except Exception:
                logger.exception("Analysis job %s crashed", job.analysis_id)
