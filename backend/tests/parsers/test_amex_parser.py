import unittest
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from domains.normalization.parsers.amex_parser import AmexParser
from decimal import Decimal

class TestAmexParser(unittest.TestCase):
    def setUp(self):
        self.parser = AmexParser()
        self.real_pdf_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', 'input_test', 'amex', 'AMEX FEBRERO 24.pdf'
        )

    def test_amex_real_parsing(self):
        if not os.path.exists(self.real_pdf_path):
            self.skipTest("PDF real de AMEX no encontrado. Saltando test.")
            
        statement = self.parser.parse(self.real_pdf_path, "TEST-AMEX-1")
        
        self.assertEqual(statement.banco, "AMEX")
        self.assertIsNotNone(statement.cuenta)
        self.assertTrue(len(statement.transacciones) > 0)
        
        cargos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "CARGO")
        abonos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "ABONO")
        
        saldo_calc = statement.saldo_inicial + abonos - cargos
        self.assertTrue(abs(saldo_calc - statement.saldo_final) <= Decimal("0.05"))
        
        print(f"\n[AMEX Parser] Cuenta: {statement.cuenta}")
        print(f"[AMEX Parser] Saldo Inicial: {statement.saldo_inicial}")
        print(f"[AMEX Parser] Transacciones extraidas: {len(statement.transacciones)}")
        print(f"[AMEX Parser] Cargos totales: {cargos}")
        print(f"[AMEX Parser] Abonos totales: {abonos}")
        print(f"[AMEX Parser] Saldo Final: {statement.saldo_final}")
        
if __name__ == '__main__':
    unittest.main()
