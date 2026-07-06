import unittest
from datetime import date, datetime
from decimal import Decimal
from domains.shared.canonical_models import CanonicalDocument, CanonicalTransaction, CanonicalXML
from domains.sat.models import SATValidationResult, SATRuleStatus
from domains.workflow.models import WorkflowEventDomain
from domains.workflow.states import WorkflowState
from domains.evidence.builder import EvidenceBuilder
from domains.evidence.models import EvidenceType, EvidenceStatus
from uuid_utils import uuid7

class TestPhase11(unittest.TestCase):
    def setUp(self):
        self.doc_uuid = str(uuid7())
        self.tx_uuid = str(uuid7())
        self.xml_uuid = str(uuid7())
        
        self.doc = CanonicalDocument(
            uuid=self.doc_uuid,
            empresa_rfc="TEST1",
            hash_sha256="hash123",
            tipo="PDF",
            tamanio_bytes=100
        )
        
        self.workflow = [
            WorkflowEventDomain(id=str(uuid7()), document_id=self.doc_uuid, estado=WorkflowState.RECEIVED, timestamp=datetime.utcnow()),
            WorkflowEventDomain(id=str(uuid7()), document_id=self.doc_uuid, estado=WorkflowState.STORED, timestamp=datetime.utcnow())
        ]
        
        self.tx = CanonicalTransaction(
            uuid=self.tx_uuid,
            statement_uuid="stmt1",
            fecha_operacion=date(2024, 1, 1),
            monto_absoluto=Decimal("100"),
            naturaleza="CARGO",
            concepto_bancario_original="PAGO"
        )
        
        self.xml = CanonicalXML(
            uuid_cfdi=self.xml_uuid,
            rfc_emisor="E",
            rfc_receptor="R",
            tipo_cfdi="I",
            subtotal=Decimal("100"),
            total=Decimal("116")
        )
        
        self.sat = SATValidationResult(uuid_cfdi=self.xml_uuid, overall_status=SATRuleStatus.PASS)

    def test_evidence_builder(self):
        builder = EvidenceBuilder(self.doc, self.workflow)
        builder.attach_transaction(self.tx)
        builder.attach_xml(self.xml)
        builder.attach_sat_validation(self.sat)
        
        pkg = builder.build()
        
        self.assertEqual(pkg.document_uuid, self.doc_uuid)
        self.assertEqual(pkg.status, EvidenceStatus.SEALED)
        self.assertEqual(pkg.sha256, "hash123")
        self.assertEqual(len(pkg.workflow_history), 2)
        
        # Check items: 1 Hash, 1 Tx, 1 XML, 1 SAT
        self.assertEqual(len(pkg.items), 4)
        
        types = [item.evidence_type for item in pkg.items]
        self.assertIn(EvidenceType.HASH_DOCUMENTAL, types)
        self.assertIn(EvidenceType.TRANSACCION_BANCARIA, types)
        self.assertIn(EvidenceType.XML_CFDI, types)
        self.assertIn(EvidenceType.RESULTADO_SAT, types)

    def test_integrity_validation_orphan_ref(self):
        builder = EvidenceBuilder(self.doc, self.workflow)
        builder.add_item(
            evidence_type=EvidenceType.PDF_REPRESENTACION,
            content={"pdf": "data"},
            references=[] # OK, no references is fine, but if reference exists it must have target
        )
        
        # Manually corrupting reference to test validation
        from domains.evidence.models import EvidenceReference
        builder.add_item(
            evidence_type=EvidenceType.PDF_REPRESENTACION,
            content={},
            references=[EvidenceReference(target_uuid="", target_type="INVALID", description="Corrupt")]
        )
        
        with self.assertRaisesRegex(ValueError, "Orphan reference"):
            builder.build()

if __name__ == "__main__":
    unittest.main()
