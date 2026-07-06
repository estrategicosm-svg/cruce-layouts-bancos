import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from infrastructure.database.orm.base import Base
from infrastructure.database.orm.models import Document, Company
from infrastructure.database.uow import SQLAlchemyUnitOfWork
from application.use_cases.workflow_service import WorkflowService
from domains.workflow.states import WorkflowState
from uuid_utils import uuid7

class TestPhase7(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.uow = SQLAlchemyUnitOfWork(self.session_factory)
        self.service = WorkflowService(self.uow)
        
        # Need a document and company for FK satisfaction
        self.company_id = str(uuid7())
        self.document_id = str(uuid7())
        
        with self.uow:
            c = Company(id=self.company_id, rfc="TEST123456T1", razon_social="Test")
            d = Document(id=self.document_id, company_id=self.company_id, hash_sha256="hash", tipo="PDF", tamanio_bytes=100)
            self.uow.companies.add(c)
            self.uow.documents.add(d)
            self.uow.commit()

    def test_valid_forward_transition(self):
        # None -> RECEIVED
        ev1 = self.service.record_transition(self.document_id, WorkflowState.RECEIVED)
        self.assertEqual(ev1.estado, WorkflowState.RECEIVED)
        
        # RECEIVED -> STORED
        ev2 = self.service.record_transition(self.document_id, WorkflowState.STORED)
        self.assertEqual(ev2.estado, WorkflowState.STORED)
        
        # Verify history
        history = self.service.get_document_history(self.document_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].estado, WorkflowState.RECEIVED)
        self.assertEqual(history[1].estado, WorkflowState.STORED)

    def test_invalid_forward_transition(self):
        self.service.record_transition(self.document_id, WorkflowState.RECEIVED)
        # Try to skip states: RECEIVED -> NORMALIZED
        with self.assertRaisesRegex(ValueError, "Invalid transition"):
            self.service.record_transition(self.document_id, WorkflowState.NORMALIZED)

    def test_fail_requires_reason(self):
        self.service.record_transition(self.document_id, WorkflowState.RECEIVED)
        
        # FAILED without reason should raise ValueError
        with self.assertRaisesRegex(ValueError, "requires a mandatory reason"):
            self.service.record_transition(self.document_id, WorkflowState.FAILED)
            
        # FAILED with reason should pass
        ev = self.service.record_transition(self.document_id, WorkflowState.FAILED, reason="Invalid PDF format")
        self.assertEqual(ev.estado, WorkflowState.FAILED)

    def test_requires_review_from_any_state(self):
        # Document can jump to REQUIRES_REVIEW from STORED if reason is provided
        self.service.record_transition(self.document_id, WorkflowState.RECEIVED)
        self.service.record_transition(self.document_id, WorkflowState.STORED)
        
        ev = self.service.record_transition(self.document_id, WorkflowState.REQUIRES_REVIEW, reason="Ambiguous data")
        self.assertEqual(ev.estado, WorkflowState.REQUIRES_REVIEW)

if __name__ == "__main__":
    unittest.main()
