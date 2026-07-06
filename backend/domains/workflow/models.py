from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from domains.workflow.states import WorkflowState

class WorkflowTransition(BaseModel):
    """
    Defines a transition from one state to another.
    """
    from_state: Optional[WorkflowState]
    to_state: WorkflowState
    reason: Optional[str] = None

class WorkflowEventDomain(BaseModel):
    """
    Pure domain representation of a Workflow Event.
    """
    id: str
    document_id: str
    estado: WorkflowState
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    mensaje: Optional[str] = None
