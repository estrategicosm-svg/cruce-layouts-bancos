from domains.banking.base import BaseBankParser, ParserResult

class IBCParser(BaseBankParser):
    def parse(self, raw_bytes: bytes, document_uuid: str) -> ParserResult:
        raise NotImplementedError("Parsing for IBC is not yet implemented.")
