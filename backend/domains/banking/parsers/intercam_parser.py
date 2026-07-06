from domains.banking.base import BaseBankParser, ParserResult

class IntercamParser(BaseBankParser):
    def parse(self, raw_bytes: bytes, document_uuid: str) -> ParserResult:
        raise NotImplementedError("Parsing for INTERCAM is not yet implemented.")
