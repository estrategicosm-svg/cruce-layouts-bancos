from domains.banking.base import BaseBankParser, ParserResult

class BBVAParser(BaseBankParser):
    def parse(self, raw_bytes: bytes, document_uuid: str) -> ParserResult:
        raise NotImplementedError("Parsing for BBVA is not yet implemented.")
