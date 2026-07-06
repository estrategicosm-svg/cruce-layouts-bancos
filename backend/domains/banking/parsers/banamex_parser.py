from domains.banking.base import BaseBankParser, ParserResult

class BanamexParser(BaseBankParser):
    def parse(self, raw_bytes: bytes, document_uuid: str) -> ParserResult:
        raise NotImplementedError("Parsing for BANAMEX is not yet implemented.")
