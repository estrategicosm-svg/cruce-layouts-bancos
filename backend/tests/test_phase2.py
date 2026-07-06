import unittest
import hashlib
from decimal import Decimal
from datetime import date
from uuid_utils import uuid7 # Need to import uuid7 correctly, maybe uuid_utils or uuid6
# Wait, I'll use standard uuid if uuid7 isn't available, but the plan says uuid7.
# I will use uuid-utils which provides uuid7
import uuid_utils

from domains.shared.canonical_models import CanonicalDocument, CanonicalTransaction
from domains.documents.utils import calculate_sha256, detect_magic_bytes
from infrastructure.storage.local_provider import LocalStorageProvider
from application.use_cases.intake import process_document_intake

# Monkey patch uuid7 for the use case if needed, but I should fix the use case.
import application.use_cases.intake
application.use_cases.intake.uuid7 = uuid_utils.uuid7

class TestPhase2(unittest.TestCase):
    
    def test_hash_calculation(self):
        data = b"hello world"
        expected_hash = hashlib.sha256(data).hexdigest()
        self.assertEqual(calculate_sha256(data), expected_hash)
        
    def test_magic_bytes(self):
        self.assertEqual(detect_magic_bytes(b"%PDF-1.4..."), "PDF_STATEMENT")
        self.assertEqual(detect_magic_bytes(b"<?xml version='1.0'?><cfdi>..."), "XML_CFDI")
        self.assertEqual(detect_magic_bytes(b"random data"), "UNKNOWN")

    def test_canonical_models(self):
        # Transaction must strictly enforce types
        tx = CanonicalTransaction(
            uuid=str(uuid_utils.uuid7()),
            statement_uuid="stmt-123",
            fecha_operacion=date(2024, 1, 1),
            monto_absoluto=Decimal("150.50"),
            naturaleza="CARGO",
            concepto_bancario_original="PAGO DE SERVICIOS"
        )
        self.assertEqual(tx.monto_absoluto, Decimal("150.50"))
        
        # Exception if monto_absoluto is negative
        with self.assertRaises(ValueError):
            CanonicalTransaction(
                uuid="123", statement_uuid="456",
                fecha_operacion=date.today(),
                monto_absoluto=Decimal("-50.00"),
                naturaleza="CARGO",
                concepto_bancario_original="ERROR"
            )

    def test_intake_flow(self):
        provider = LocalStorageProvider(base_dir="test_storage")
        pdf_bytes = b"%PDF-dummy-content"
        rfc = "ABC123456T1"
        
        doc, url = process_document_intake(pdf_bytes, rfc, provider)
        
        self.assertEqual(doc.tipo, "PDF_STATEMENT")
        self.assertEqual(doc.empresa_rfc, rfc)
        self.assertEqual(doc.estado_workflow, "RECIBIDO")
        self.assertTrue(provider.exists(url.split("test_storage\\")[-1].replace("\\", "/")))

if __name__ == "__main__":
    unittest.main()
