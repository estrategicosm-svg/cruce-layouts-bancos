from typing import Optional, List
from domains.shared.uow import UnitOfWork
from domains.workflow.states import WorkflowState
from domains.workflow.models import WorkflowEventDomain
from domains.workflow.transitions import validate_transition
from infrastructure.database.orm.models import WorkflowEvent
from uuid_utils import uuid7

class WorkflowService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    def record_transition(self, document_id: str, to_state: WorkflowState, reason: Optional[str] = None) -> WorkflowEventDomain:
        """
        Validates and records a state transition for a document.
        Uses UoW for transaction boundaries.
        """
        with self.uow:
            # 1. Get current state (last event for this document)
            events = self.uow.workflow_events.get_by_document_id(document_id)
            current_state = None
            if events:
                # Sort by timestamp to get the latest
                latest_event = sorted(events, key=lambda e: e.timestamp, reverse=True)[0]
                current_state = WorkflowState(latest_event.estado)

            # 2. Validate transition rules
            validate_transition(current_state, to_state, reason)

            # 3. Create ORM Event and persist
            event_id = str(uuid7())
            orm_event = WorkflowEvent(
                id=event_id,
                document_id=document_id,
                estado=to_state.value,
                mensaje=reason
            )
            self.uow.workflow_events.add(orm_event)
            self.uow.commit()
            
            # 4. Return Domain Event
            return WorkflowEventDomain(
                id=orm_event.id,
                document_id=orm_event.document_id,
                estado=WorkflowState(orm_event.estado),
                timestamp=orm_event.timestamp,
                mensaje=orm_event.mensaje
            )

    def get_document_history(self, document_id: str) -> List[WorkflowEventDomain]:
        """
        Returns the full state history of a document.
        """
        with self.uow:
            events = self.uow.workflow_events.get_by_document_id(document_id)
            sorted_events = sorted(events, key=lambda e: e.timestamp)
            return [
                WorkflowEventDomain(
                    id=e.id,
                    document_id=e.document_id,
                    estado=WorkflowState(e.estado),
                    timestamp=e.timestamp,
                    mensaje=e.mensaje
                ) for e in sorted_events
            ]
