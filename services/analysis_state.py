"""State pattern for VideoAnalysis (State Machine Diagram).

    PENDING --start--> PROCESSING --complete--> COMPLETED
       |                   |-------fail-------> FAILED
       |--cancel--> CANCELLED <--cancel--|
       |--fail----> FAILED

Each state decides which transitions are legal; illegal ones raise
``InvalidStateTransition`` (HTTP 409) instead of silently corrupting data.
"""

from __future__ import annotations

from abc import ABC

from models import VideoAnalysis, utc_now
from errors import DomainError


class InvalidStateTransition(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "INVALID_ANALYSIS_STATE")


class AnalysisState(ABC):
    name: str = ""
    is_terminal: bool = False

    def _deny(self, action: str) -> None:
        raise InvalidStateTransition(f"Cannot {action} an analysis in state {self.name}.")

    def start(self, machine: "AnalysisStateMachine") -> None:
        self._deny("start")

    def complete(self, machine: "AnalysisStateMachine", warning: str | None) -> None:
        self._deny("complete")

    def fail(self, machine: "AnalysisStateMachine", reason: str) -> None:
        self._deny("fail")

    def cancel(self, machine: "AnalysisStateMachine") -> None:
        self._deny("cancel")


class PendingState(AnalysisState):
    name = "PENDING"

    def start(self, machine):
        machine.analysis.started_at = utc_now()
        machine.transition_to(ProcessingState())

    def fail(self, machine, reason):
        machine.finish(FailedState(), reason)

    def cancel(self, machine):
        machine.finish(CancelledState(), "Cancelado antes de iniciar el procesamiento.")


class ProcessingState(AnalysisState):
    name = "PROCESSING"

    def complete(self, machine, warning):
        machine.finish(CompletedState(), warning)

    def fail(self, machine, reason):
        machine.finish(FailedState(), reason)

    def cancel(self, machine):
        machine.finish(CancelledState(), "Cancelado durante el procesamiento; los resultados se descartaron.")


class CompletedState(AnalysisState):
    name = "COMPLETED"
    is_terminal = True


class FailedState(AnalysisState):
    name = "FAILED"
    is_terminal = True


class CancelledState(AnalysisState):
    name = "CANCELLED"
    is_terminal = True


STATES: dict[str, type[AnalysisState]] = {
    state.name: state
    for state in (PendingState, ProcessingState, CompletedState, FailedState, CancelledState)
}


class AnalysisStateMachine:
    """Context object: wraps the ORM entity and delegates behaviour to its current state."""

    def __init__(self, analysis: VideoAnalysis) -> None:
        self.analysis = analysis
        self._state: AnalysisState = STATES[analysis.status]()

    @property
    def state(self) -> AnalysisState:
        return self._state

    def transition_to(self, state: AnalysisState) -> None:
        self._state = state
        self.analysis.status = state.name

    def finish(self, state: AnalysisState, message: str | None) -> None:
        self.analysis.completed_at = utc_now()
        if message:
            self.analysis.warning_message = message[:255]
        self.transition_to(state)

    def start(self) -> None:
        self._state.start(self)

    def complete(self, warning: str | None = None) -> None:
        self._state.complete(self, warning)

    def fail(self, reason: str) -> None:
        self._state.fail(self, reason)

    def cancel(self) -> None:
        self._state.cancel(self)
