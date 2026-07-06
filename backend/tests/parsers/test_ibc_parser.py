import unittest
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from domains.normalization.parsers.ibc_parser import IBCParser
from decimal import Decimal

class TestIBCParser(unittest.TestCase):
    def setUp(self):
        self.parser = IBCParser()
        self.real_pdf_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', 'input_test', 'ibc', 'IBC FEBRERO 24.pdf'
        )

    def test_ibc_real_parsing(self):
        if not os.path.exists(self.real_pdf_path):
            self.skipTest("PDF real de IBC no encontrado. Saltando test.")
            
        statement = self.parser.parse(self.real_pdf_path, "TEST-IBC-1")
        
        self.assertEqual(statement.banco, "IBC")
        self.assertIsNotNone(statement.cuenta)
        self.assertTrue(len(statement.transacciones) > 0)
        
        cargos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "CARGO")
        abonos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "ABONO")
        
        saldo_calc = statement.saldo_inicial + abonos - cargos
        self.assertTrue(abs(saldo_calc - statement.saldo_final) <= Decimal("0.05"))
        
        print(f"\n[IBC Parser] Cuenta: {statement.cuenta}")
        print(f"[IBC Parser] Saldo Inicial: {statement.saldo_inicial}")
        print(f"[IBC Parser] Transacciones extraidas: {len(statement.transacciones)}")
        print(f"[IBC Parser] Cargos totales: {cargos}")
        print(f"[IBC Parser] Abonos totales: {abonos}")
        print(f"[IBC Parser] Saldo Final: {statement.saldo_final}")
        
if __name__ == '__main__':
    unittest.main()
