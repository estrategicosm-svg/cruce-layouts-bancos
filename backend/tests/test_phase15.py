import unittest
from decimal import Decimal
from datetime import date
import time
from domains.shared.canonical_models import CanonicalTransaction, CanonicalXML
from domains.conciliation.tolerance import ToleranceEngine
from domains.conciliation.strategies import (
    UUIDMatchStrategy, ReferenceMatchStrategy, SubsetSumMatchStrategy,
    ManyToOneMatchStrategy, SplitPaymentMatchStrategy
)
from domains.conciliation.engine import ConciliationEngine

class TestPhase15(unittest.TestCase):
    def setUp(self):
        tolerance = ToleranceEngine(allowed_days_diff=0, allowed_cents_diff=Decimal("0.0"))
        self.engine = ConciliationEngine(strategies=[
            UUIDMatchStrategy(tolerance),
            ReferenceMatchStrategy(tolerance),
            SubsetSumMatchStrategy(tolerance),
            ManyToOneMatchStrategy(tolerance),
            SplitPaymentMatchStrategy(tolerance)
        ])

    def test_subset_sum_basic(self):
        # 1 deposito de 25000, 3 facturas (8000, 7000, 10000) y ruido
        tx = CanonicalTransaction(
            uuid="TX1", statement_uuid="S1", fecha_operacion=date(2024,1,1),
            monto_absoluto=Decimal("25000.00"), naturaleza="ABONO", concepto_bancario_original="PAGO"
        )
        xmls = [
            CanonicalXML(uuid_cfdi="X1", rfc_emisor="E", rfc_receptor="R", tipo_cfdi="I", subtotal=Decimal("8000.00"), total=Decimal("8000.00")),
            CanonicalXML(uuid_cfdi="X2", rfc_emisor="E", rfc_receptor="R", tipo_cfdi="I", subtotal=Decimal("7000.00"), total=Decimal("7000.00")),
            CanonicalXML(uuid_cfdi="X3", rfc_emisor="E", rfc_receptor="R", tipo_cfdi="I", subtotal=Decimal("10000.00"), total=Decimal("10000.00")),
            CanonicalXML(uuid_cfdi="X4", rfc_emisor="E", rfc_receptor="R", tipo_cfdi="I", subtotal=Decimal("5000.00"), total=Decimal("5000.00")) # Ruido
        ]
        
        result = self.engine.conciliate([tx], xmls)
        self.assertEqual(len(result.matches), 1)
        match = result.matches[0]
        self.assertEqual(match.strategy_used, "SUBSET_SUM")
        self.assertEqual(len(match.xmls), 3)
        self.assertEqual(match.confidence, 0.75)

    def test_subset_sum_performance(self):
        # Generar 30 XMLs (El ruido masivo mata la fuerza bruta ingenua)
        tx = CanonicalTransaction(
            uuid="TX1", statement_uuid="S1", fecha_operacion=date(2024,1,1),
            monto_absoluto=Decimal("15000.00"), naturaleza="ABONO", concepto_bancario_original="PAGO"
        )
        
        xmls = []
        for i in range(28):
            xmls.append(CanonicalXML(uuid_cfdi=f"X_NO_{i}", rfc_emisor="E", rfc_receptor="R", tipo_cfdi="I", subtotal=Decimal("100.00"), total=Decimal("100.00")))
        
        # Estas 2 suman 15000
        xmls.append(CanonicalXML(uuid_cfdi="X_SI_1", rfc_emisor="E", rfc_receptor="R", tipo_cfdi="I", subtotal=Decimal("7000.00"), total=Decimal("7000.00")))
        xmls.append(CanonicalXML(uuid_cfdi="X_SI_2", rfc_emisor="E", rfc_receptor="R", tipo_cfdi="I", subtotal=Decimal("8000.00"), total=Decimal("8000.00")))
        
        start_time = time.time()
        result = self.engine.conciliate([tx], xmls)
        end_time = time.time()
        
        # Debe tomar menos de 1 segundo si está optimizado (con podas y sort desc)
        self.assertLess(end_time - start_time, 1.0)
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(len(result.matches[0].xmls), 2)

    def test_many_to_one(self):
        tx1 = CanonicalTransaction(uuid="TX1", statement_uuid="S1", fecha_operacion=date(2024,1,1), monto_absoluto=Decimal("400.00"), naturaleza="ABONO", concepto_bancario_original="P1")
        tx2 = CanonicalTransaction(uuid="TX2", statement_uuid="S1", fecha_operacion=date(2024,1,2), monto_absoluto=Decimal("600.00"), naturaleza="ABONO", concepto_bancario_original="P2")
        xml = CanonicalXML(uuid_cfdi="X1", rfc_emisor="E", rfc_receptor="R", tipo_cfdi="I", subtotal=Decimal("1000.00"), total=Decimal("1000.00"))
        
        result = self.engine.conciliate([tx1, tx2], [xml])
        self.assertEqual(len(result.matches), 1)
        match = result.matches[0]
        self.assertEqual(match.strategy_used, "MANY_TO_ONE")
        self.assertEqual(len(match.transactions), 2)
        
    def test_split_payment(self):
        # Pago parcial: TX de 500 para un XML de 1500, pero TIENE que coincidir UUID o Referencia
        tx = CanonicalTransaction(uuid="TX1", statement_uuid="S1", fecha_operacion=date(2024,1,1), monto_absoluto=Decimal("500.00"), naturaleza="ABONO", concepto_bancario_original="PAGO FACTURA X1")
        xml = CanonicalXML(uuid_cfdi="X1", rfc_emisor="E", rfc_receptor="R", tipo_cfdi="I", subtotal=Decimal("1500.00"), total=Decimal("1500.00"))
        
        result = self.engine.conciliate([tx], [xml])
        self.assertEqual(len(result.matches), 1)
        match = result.matches[0]
        self.assertEqual(match.strategy_used, "SPLIT_PAYMENT")
        self.assertEqual(match.partial_applied_amount, 500.0)
        self.assertEqual(match.partial_remaining_amount, 1000.0)
        self.assertEqual(match.confidence, 0.85)

    def test_priority_resolver_avoids_overlap(self):
        # Una TX tiene UUID match con X1, pero sumada con TX2 cuadra con X1 (Many to One). 
        # Priority resolver debe elegir UUID (prioridad 100) sobre ManyToOne (prioridad 75)
        tx1 = CanonicalTransaction(uuid="TX1", statement_uuid="S1", fecha_operacion=date(2024,1,1), monto_absoluto=Decimal("1000.00"), naturaleza="ABONO", concepto_bancario_original="PAGO X1")
        tx2 = CanonicalTransaction(uuid="TX2", statement_uuid="S1", fecha_operacion=date(2024,1,2), monto_absoluto=Decimal("0.00"), naturaleza="ABONO", concepto_bancario_original="")
        xml = CanonicalXML(uuid_cfdi="X1", rfc_emisor="E", rfc_receptor="R", tipo_cfdi="I", subtotal=Decimal("1000.00"), total=Decimal("1000.00"))
        
        result = self.engine.conciliate([tx1, tx2], [xml])
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].strategy_used, "UUID")

if __name__ == "__main__":
    unittest.main()
