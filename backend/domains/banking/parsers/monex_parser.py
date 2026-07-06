from domains.banking.base import BaseBankParser, ParserResult

class MonexParser(BaseBankParser):
    def parse(self, raw_bytes: bytes, document_uuid: str) -> ParserResult:
        raise NotImplementedError("Parsing for MONEX is not yet implemented.")
