import unittest
from decimal import Decimal
from datetime import date
from domains.shared.canonical_models import CanonicalTransaction, CanonicalXML
from domains.conciliation.tolerance import ToleranceEngine
from domains.conciliation.strategies import ExactMatchStrategy, UUIDMatchStrategy, ReferenceMatchStrategy
from domains.conciliation.resolver import ConciliationEngine, ConflictResolver
from domains.conciliation.models import MatchStatus

class TestPhase8(unittest.TestCase):
    def setUp(self):
        self.tolerance = ToleranceEngine(allowed_cents_diff=Decimal("0.05"), allowed_days_diff=2)
        self.strategies = [
            ExactMatchStrategy(self.tolerance),
            UUIDMatchStrategy(self.tolerance),
            ReferenceMatchStrategy(self.tolerance)
        ]
        self.resolver = ConflictResolver()
        self.engine = ConciliationEngine(self.strategies, self.resolver)
        
        self.tx1 = CanonicalTransaction(
            uuid="tx1", statement_uuid="stmt1", fecha_operacion=date(2024, 1, 15),
            monto_absoluto=Decimal("1500.00"), naturaleza="CARGO",
            concepto_bancario_original="PAGO PROVEEDOR UUID A1B2C3D4-1234-5678-9ABC-DEF012345678",
            referencia_numerica_limpia=None
        )
        
        self.tx2 = CanonicalTransaction(
            uuid="tx2", statement_uuid="stmt1", fecha_operacion=date(2024, 1, 16),
            monto_absoluto=Decimal("2000.00"), naturaleza="CARGO",
            concepto_bancario_original="PAGO FACTURA REF 99999",
            referencia_numerica_limpia="99999"
        )
        
        self.xml1 = CanonicalXML(
            uuid_cfdi="A1B2C3D4-1234-5678-9ABC-DEF012345678",
            rfc_emisor="EMISOR1", rfc_receptor="RECEP1",
            tipo_cfdi="I", subtotal=Decimal("1293.10"), total=Decimal("1500.00")
        )
        
        self.xml2 = CanonicalXML(
            uuid_cfdi="Z9Y8X7W6-1234-5678-9ABC-DEF012399999",
            rfc_emisor="EMISOR2", rfc_receptor="RECEP2",
            tipo_cfdi="I", subtotal=Decimal("1724.13"), total=Decimal("2000.00")
        )

    def test_uuid_match(self):
        result = self.engine.reconcile([self.tx1], [self.xml1])
        self.assertEqual(len(result.matches), 1)
        match = result.matches[0]
        self.assertEqual(match.status, MatchStatus.EXACT)
        self.assertEqual(match.explanations[0].rule_name, "UUID_MATCH")
        
    def test_reference_match(self):
        result = self.engine.reconcile([self.tx2], [self.xml2])
        self.assertEqual(len(result.matches), 1)
        match = result.matches[0]
        self.assertEqual(match.status, MatchStatus.PARTIAL)
        self.assertEqual(match.explanations[0].rule_name, "REFERENCE_MATCH")
        
    def test_unmatched(self):
        # amount differs
        self.xml2.total = Decimal("3000.00")
        result = self.engine.reconcile([self.tx2], [self.xml2])
        self.assertEqual(len(result.matches), 0)
        self.assertEqual(len(result.unmatched_transactions), 1)
        self.assertEqual(len(result.unmatched_xmls), 1)

    def test_conflict(self):
        # tx2 has ref 99999 and amount 2000.00. Create another XML with same amount and ending in 99999 to cause conflict.
        xml3 = CanonicalXML(
            uuid_cfdi="C3B2A1-1234-5678-9ABC-DEF012399999",
            rfc_emisor="EMISOR3", rfc_receptor="RECEP3",
            tipo_cfdi="I", subtotal=Decimal("1724.13"), total=Decimal("2000.00")
        )
        result = self.engine.reconcile([self.tx2], [self.xml2, xml3])
        # It will match both XMLs in Candidate phase, then ConflictResolver marks them as CONFLICT
        # Result matches len should be 2, but both CONFLICT
        self.assertEqual(len(result.matches), 2)
        self.assertTrue(all(m.status == MatchStatus.CONFLICT for m in result.matches))
        
if __name__ == "__main__":
    unittest.main()
