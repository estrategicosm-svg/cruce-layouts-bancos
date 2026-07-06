import unittest
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from domains.normalization.parsers.banamex_parser import BanamexParser
from decimal import Decimal

class TestBanamexParser(unittest.TestCase):
    def setUp(self):
        self.parser = BanamexParser()
        self.real_pdf_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', 'input_test', 'banamex', 'BMX FEBRERO 24.pdf'
        )

    def test_banamex_real_parsing(self):
        if not os.path.exists(self.real_pdf_path):
            self.skipTest("PDF real de Banamex no encontrado. Saltando test.")
            
        statement = self.parser.parse(self.real_pdf_path, "TEST-BMX-1")
        
        self.assertEqual(statement.banco, "BANAMEX")
        self.assertIsNotNone(statement.cuenta)
        self.assertTrue(len(statement.transacciones) > 0)
        
        cargos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "CARGO")
        abonos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "ABONO")
        
        saldo_calc = statement.saldo_inicial + abonos - cargos
        self.assertTrue(abs(saldo_calc - statement.saldo_final) <= Decimal("0.05"))
        
        print(f"\n[Banamex Parser] Cuenta: {statement.cuenta}")
        print(f"[Banamex Parser] Saldo Inicial: {statement.saldo_inicial}")
        print(f"[Banamex Parser] Transacciones extraidas: {len(statement.transacciones)}")
        print(f"[Banamex Parser] Cargos totales: {cargos}")
        print(f"[Banamex Parser] Abonos totales: {abonos}")
        print(f"[Banamex Parser] Saldo Final: {statement.saldo_final}")
        
if __name__ == '__main__':
    unittest.main()
