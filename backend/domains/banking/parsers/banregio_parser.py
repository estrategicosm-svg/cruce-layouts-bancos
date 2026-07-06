from domains.banking.base import BaseBankParser, ParserResult

class BanregioParser(BaseBankParser):
    def parse(self, raw_bytes: bytes, document_uuid: str) -> ParserResult:
        raise NotImplementedError("Parsing for BANREGIO is not yet implemented.")
