from domains.banking.base import BaseBankParser, ParserResult

class AMEXParser(BaseBankParser):
    def parse(self, raw_bytes: bytes, document_uuid: str) -> ParserResult:
        raise NotImplementedError("Parsing for AMEX is not yet implemented.")
