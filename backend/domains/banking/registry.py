from typing import Dict, Type
from domains.banking.base import BaseBankParser
from domains.banking.exceptions import UnsupportedBankError
from domains.banking.parsers.bbva_parser import BBVAParser
from domains.banking.parsers.banamex_parser import BanamexParser
from domains.banking.parsers.banregio_parser import BanregioParser
from domains.banking.parsers.bajio_parser import BajioParser
from domains.banking.parsers.ibc_parser import IBCParser
from domains.banking.parsers.amex_parser import AMEXParser
from domains.banking.parsers.monex_parser import MonexParser
from domains.banking.parsers.intercam_parser import IntercamParser

class ParserRegistry:
    """
    Factory / Registry for bank parsers.
    Instantiates the correct parser based on the bank identifier.
    """
    
    _parsers: Dict[str, Type[BaseBankParser]] = {
        "BBVA": BBVAParser,
        "BANAMEX": BanamexParser,
        "BANREGIO": BanregioParser,
        "BAJIO": BajioParser,
        "IBC": IBCParser,
        "AMEX": AMEXParser,
        "MONEX": MonexParser,
        "INTERCAM": IntercamParser
    }

    @classmethod
    def get_parser(cls, bank_identifier: str) -> BaseBankParser:
        """
        Returns an instance of the corresponding parser.
        Raises UnsupportedBankError if the bank is not registered.
        """
        parser_class = cls._parsers.get(bank_identifier.upper())
        if not parser_class:
            raise UnsupportedBankError(f"No parser registered for bank: {bank_identifier}")
        return parser_class()
