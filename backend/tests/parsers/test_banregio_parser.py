import unittest
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from domains.normalization.parsers.banregio_parser import BanregioParser
from decimal import Decimal

class TestBanregioParser(unittest.TestCase):
    def setUp(self):
        self.parser = BanregioParser()
        self.real_pdf_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', 'input_test', 'banregio', 'BANREGIO FEBRERO 24.pdf'
        )

    def test_banregio_real_parsing(self):
        if not os.path.exists(self.real_pdf_path):
            self.skipTest("PDF real de Banregio no encontrado. Saltando test.")
            
        statement = self.parser.parse(self.real_pdf_path, "TEST-BRG-1")
        
        self.assertEqual(statement.banco, "BANREGIO")
        self.assertIsNotNone(statement.cuenta)
        self.assertTrue(len(statement.transacciones) > 0)
        
        cargos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "CARGO")
        abonos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "ABONO")
        
        saldo_calc = statement.saldo_inicial + abonos - cargos
        self.assertTrue(abs(saldo_calc - statement.saldo_final) <= Decimal("0.05"))
        
        print(f"\n[Banregio Parser] Cuenta: {statement.cuenta}")
        print(f"[Banregio Parser] Saldo Inicial: {statement.saldo_inicial}")
        print(f"[Banregio Parser] Transacciones extraidas: {len(statement.transacciones)}")
        print(f"[Banregio Parser] Cargos totales: {cargos}")
        print(f"[Banregio Parser] Abonos totales: {abonos}")
        print(f"[Banregio Parser] Saldo Final: {statement.saldo_final}")
        
if __name__ == '__main__':
    unittest.main()
