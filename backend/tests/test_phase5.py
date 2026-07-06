import unittest
from datetime import date
from decimal import Decimal
from domains.normalization.validators import (
    validate_currency, validate_date, validate_amount,
    validate_nature, validate_rfc, validate_uuid
)
from domains.normalization.cleaners import extract_clean_reference

class TestPhase5(unittest.TestCase):
    
    def test_currency_validator(self):
        self.assertEqual(validate_currency(" mxn "), "MXN")
        self.assertEqual(validate_currency("usd"), "USD")
        self.assertEqual(validate_currency(""), "MXN")
        with self.assertRaises(ValueError):
            validate_currency("GBP")
            
    def test_date_validator(self):
        self.assertEqual(validate_date("2024-05-15"), date(2024, 5, 15))
        self.assertEqual(validate_date("15/05/2024"), date(2024, 5, 15))
        with self.assertRaises(ValueError):
            validate_date("15-05-24") # Not supported without full year
            
    def test_amount_validator(self):
        self.assertEqual(validate_amount("1,234.56"), Decimal("1234.56"))
        self.assertEqual(validate_amount(1500.0), Decimal("1500"))
        with self.assertRaises(ValueError):
            validate_amount("-50")
        with self.assertRaises(ValueError):
            validate_amount("abc")
            
    def test_nature_validator(self):
        self.assertEqual(validate_nature(" cargo "), "CARGO")
        self.assertEqual(validate_nature("Abono"), "ABONO")
        with self.assertRaises(ValueError):
            validate_nature("DEBITO")
            
    def test_rfc_validator(self):
        self.assertEqual(validate_rfc("XAXX010101000"), "XAXX010101000")
        self.assertEqual(validate_rfc(" EKU9003173C9 "), "EKU9003173C9")
        with self.assertRaises(ValueError):
            validate_rfc("INVALIDRFC")
            
    def test_uuid_validator(self):
        valid = "F35B6D51-7896-4F7F-B28E-6C0C9FA9F200"
        self.assertEqual(validate_uuid(valid.lower()), valid)
        with self.assertRaises(ValueError):
            validate_uuid("NOT-A-UUID")
            
    def test_reference_cleaner(self):
        # Marker testing
        self.assertEqual(extract_clean_reference("CLAVE DE RASTREO: 1234567"), "1234567")
        self.assertEqual(extract_clean_reference("AUT#88888"), "88888")
        self.assertEqual(extract_clean_reference("SPEI RECIBIDO REF 999999"), "999999")
        # Fallback testing
        self.assertEqual(extract_clean_reference("PAGO PROVEEDOR 12345678"), "12345678")
        # Ignore dates
        self.assertEqual(extract_clean_reference("PAGO DEL 12/05/2024 OP 111111"), "111111")
        self.assertIsNone(extract_clean_reference("PAGO DEL 12/05/2024"))

if __name__ == "__main__":
    unittest.main()
