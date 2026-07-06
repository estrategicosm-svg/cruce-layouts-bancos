import unittest
import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from domains.normalization.parsers.monex_parser import MonexParser
from decimal import Decimal

class TestMonexParser(unittest.TestCase):
    def setUp(self):
        self.parser = MonexParser()
        self.real_pdf_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', 'input_test', 'monex', 'MONEX FEBRERO 24.pdf'
        )

    def test_monex_real_parsing(self):
        if not os.path.exists(self.real_pdf_path):
            self.skipTest("PDF real de Monex no encontrado. Saltando test.")
            
        start_time = time.time()
        statement = self.parser.parse(self.real_pdf_path, "TEST-MONEX-1")
        elapsed = time.time() - start_time
        
        self.assertEqual(statement.banco, "MONEX")
        self.assertIsNotNone(statement.cuenta)
        self.assertTrue(len(statement.transacciones) > 0)
        
        cargos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "CARGO")
        abonos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "ABONO")
        
        saldo_calc = statement.saldo_inicial + abonos - cargos
        diff = abs(saldo_calc - statement.saldo_final)
        self.assertTrue(diff <= Decimal("0.05"))
        
        print(f"\n[Monex Parser] Tiempo promedio: {elapsed:.2f}s")
        print(f"[Monex Parser] Cuenta: {statement.cuenta}")
        print(f"[Monex Parser] Moneda: {statement.moneda}")
        print(f"[Monex Parser] Saldo Inicial: {statement.saldo_inicial}")
        print(f"[Monex Parser] Transacciones extraidas: {len(statement.transacciones)}")
        print(f"[Monex Parser] Cargos totales: {cargos}")
        print(f"[Monex Parser] Abonos totales: {abonos}")
        print(f"[Monex Parser] Saldo Final: {statement.saldo_final}")
        print(f"[Monex Parser] Diferencia matematica: {diff}")
        print(f"[Monex Parser] Errores encontrados: Ninguno")
        
if __name__ == '__main__':
    unittest.main()
