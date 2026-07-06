import unittest
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from domains.normalization.parsers.bbva_parser import BBVAParser
from domains.normalization.parsers.base_parser import ParseError, MathIntegrityError
from decimal import Decimal

class TestBBVAParser(unittest.TestCase):
    def setUp(self):
        self.parser = BBVAParser()
        self.real_pdf_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', 'input_test', 'bbva', 'BBVA FEBRERO 24.pdf'
        )

    def test_bbva_real_parsing(self):
        if not os.path.exists(self.real_pdf_path):
            self.skipTest("PDF real de BBVA no encontrado. Saltando test.")
            
        # Ejecutar Parser
        statement = self.parser.parse(self.real_pdf_path, "TEST-DOC-1")
        
        # Validar Estructura
        self.assertEqual(statement.banco, "BBVA")
        self.assertIsNotNone(statement.cuenta)
        self.assertTrue(len(statement.transacciones) > 0)
        
        # El validador matemático interno ya corrió en el parser.
        # Volvemos a probar manualmente para el assert.
        cargos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "CARGO")
        abonos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "ABONO")
        
        saldo_calc = statement.saldo_inicial + abonos - cargos
        self.assertTrue(abs(saldo_calc - statement.saldo_final) <= Decimal("0.05"))
        
        print(f"\n[BBVA Parser] Cuenta: {statement.cuenta}")
        print(f"[BBVA Parser] Saldo Inicial: {statement.saldo_inicial}")
        print(f"[BBVA Parser] Transacciones extraidas: {len(statement.transacciones)}")
        print(f"[BBVA Parser] Cargos totales: {cargos}")
        print(f"[BBVA Parser] Abonos totales: {abonos}")
        print(f"[BBVA Parser] Saldo Final: {statement.saldo_final}")
        
if __name__ == '__main__':
    unittest.main()
