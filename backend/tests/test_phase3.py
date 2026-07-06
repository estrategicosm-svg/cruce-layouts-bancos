import unittest
import inspect
from domains.banking.base import BaseBankParser, ParserResult
from domains.banking.exceptions import UnsupportedBankError
from domains.banking.registry import ParserRegistry

class TestPhase3(unittest.TestCase):
    
    def test_unsupported_bank_error(self):
        with self.assertRaises(UnsupportedBankError):
            ParserRegistry.get_parser("NONEXISTENT_BANK")

    def test_registry_returns_stubs(self):
        banks = ["BBVA", "BANAMEX", "BANREGIO", "BAJIO", "IBC", "AMEX", "MONEX", "INTERCAM"]
        for bank in banks:
            parser = ParserRegistry.get_parser(bank)
            self.assertIsInstance(parser, BaseBankParser)
            # Ensure the parse method is overridden
            self.assertTrue(hasattr(parser, "parse"))

    def test_parse_signature_strictness(self):
        # We ensure that BaseBankParser specifies ParserResult as return type
        sig = inspect.signature(BaseBankParser.parse)
        self.assertEqual(sig.return_annotation, ParserResult)

    def test_stubs_raise_not_implemented(self):
        # We must not process data yet (Fase 3 boundary)
        parser = ParserRegistry.get_parser("BBVA")
        with self.assertRaises(NotImplementedError):
            parser.parse(b"dummy_data", "doc_uuid_123")

if __name__ == "__main__":
    unittest.main()
