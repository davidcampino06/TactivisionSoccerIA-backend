import pytest

from data_structures import DoublyLinkedList, EmptyStructureError, Queue, Stack
from models import VideoAnalysis
from services.ai_client import AIResponseError, AIResponseValidator, RetryingAIClient, AIServiceError, AIAnalysisClient
from services.analysis_state import AnalysisStateMachine, InvalidStateTransition
from services.tactical_versions import TacticalConfigurationPrototype
from singleton import SingletonMeta


def test_stack_queue_and_doubly_linked_list():
    stack = Stack([1, 2])
    assert stack.pop() == 2 and stack.peek() == 1
    with pytest.raises(EmptyStructureError):
        Stack().pop()
    queue = Queue()
    queue.enqueue("a"), queue.enqueue("b")
    assert queue.position_of("b") == 2 and queue.dequeue() == "a"
    linked = DoublyLinkedList()
    first = linked.append(1)
    linked.append(2)
    linked.prepend(0)
    assert list(linked) == [0, 1, 2] and list(linked.reversed()) == [2, 1, 0]
    linked.remove(first)
    assert list(linked) == [0, 2] and len(linked) == 2


def test_singleton_returns_same_instance():
    class Registry(metaclass=SingletonMeta):
        pass
    assert Registry() is Registry()


def test_state_machine_transitions():
    analysis = VideoAnalysis(status="PENDING")
    machine = AnalysisStateMachine(analysis)
    machine.start()
    assert analysis.status == "PROCESSING" and analysis.started_at
    machine.complete("ok")
    assert analysis.status == "COMPLETED"
    with pytest.raises(InvalidStateTransition):
        machine.cancel()


def test_prototype_clone_is_independent():
    original = TacticalConfigurationPrototype({"lines": {"defense": 40}})
    clone = original.clone().apply_patch({"lines": {"defense": 50}, "note": "new"})
    assert original.configuration == {"lines": {"defense": 40}}
    assert clone.configuration == {"lines": {"defense": 50}, "note": "new"}


def test_validator_rejects_mode_mismatch():
    with pytest.raises(AIResponseError):
        AIResponseValidator("REAL_VIDEO_ANALYSIS").validate({"status": "COMPLETED"})


def test_retry_decorator_retries_only_unreachable():
    class Flaky(AIAnalysisClient):
        calls = 0
        def analyze(self, video_path, options):
            Flaky.calls += 1
            if Flaky.calls < 3:
                raise AIServiceError("AI Service unreachable: refused")
            return {"ok": True}
    assert RetryingAIClient(Flaky(), attempts=3, backoff_seconds=0).analyze(None, {}) == {"ok": True}
    assert Flaky.calls == 3
