import unittest
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from domains.normalization.parsers.bajio_parser import BajioParser
from decimal import Decimal

class TestBajioParser(unittest.TestCase):
    def setUp(self):
        self.parser = BajioParser()
        self.real_pdf_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', 'input_test', 'bajio', 'BAJIO FEBRERO 24.pdf'
        )

    def test_bajio_real_parsing(self):
        if not os.path.exists(self.real_pdf_path):
            self.skipTest("PDF real de Bajio no encontrado. Saltando test.")
            
        statement = self.parser.parse(self.real_pdf_path, "TEST-BAJ-1")
        
        self.assertEqual(statement.banco, "BAJIO")
        self.assertIsNotNone(statement.cuenta)
        self.assertTrue(len(statement.transacciones) > 0)
        
        cargos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "CARGO")
        abonos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "ABONO")
        
        saldo_calc = statement.saldo_inicial + abonos - cargos
        self.assertTrue(abs(saldo_calc - statement.saldo_final) <= Decimal("0.05"))
        
        print(f"\n[Bajio Parser] Cuenta: {statement.cuenta}")
        print(f"[Bajio Parser] Saldo Inicial: {statement.saldo_inicial}")
        print(f"[Bajio Parser] Transacciones extraidas: {len(statement.transacciones)}")
        print(f"[Bajio Parser] Cargos totales: {cargos}")
        print(f"[Bajio Parser] Abonos totales: {abonos}")
        print(f"[Bajio Parser] Saldo Final: {statement.saldo_final}")
        
if __name__ == '__main__':
    unittest.main()
