from domains.banking.base import BaseBankParser, ParserResult

class BajioParser(BaseBankParser):
    def parse(self, raw_bytes: bytes, document_uuid: str) -> ParserResult:
        raise NotImplementedError("Parsing for BAJIO is not yet implemented.")
