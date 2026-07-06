from typing import Optional
from domains.workflow.states import WorkflowState

# Define deterministic valid transitions forward
VALID_FORWARD_TRANSITIONS = {
    None: [WorkflowState.RECEIVED],
    WorkflowState.RECEIVED: [WorkflowState.STORED],
    WorkflowState.STORED: [WorkflowState.CLASSIFIED],
    WorkflowState.CLASSIFIED: [WorkflowState.PARSED],
    WorkflowState.PARSED: [WorkflowState.NORMALIZED],
    WorkflowState.NORMALIZED: [WorkflowState.VALIDATED],
    WorkflowState.VALIDATED: [WorkflowState.READY_FOR_CONCILIATION]
}

def validate_transition(current_state: Optional[WorkflowState], next_state: WorkflowState, reason: Optional[str] = None) -> None:
    """
    Validates if a transition is allowed according to the state machine rules.
    Raises ValueError if transition is invalid or lacks required reason.
    """
    if next_state in [WorkflowState.FAILED, WorkflowState.REQUIRES_REVIEW]:
        if not reason or not reason.strip():
            raise ValueError(f"Transition to {next_state.value} requires a mandatory reason.")
        return # Always allowed from anywhere

    allowed_next_states = VALID_FORWARD_TRANSITIONS.get(current_state, [])
    if next_state not in allowed_next_states:
        curr_str = current_state.value if current_state else "None"
        raise ValueError(f"Invalid transition from {curr_str} to {next_state.value}")
