from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import List

from domains.shared.canonical_models import CanonicalStatement

class ParserResult(BaseModel):
    """
    Standard result returned by any bank parser.
    Ensures that the output is always a CanonicalStatement,
    not raw dictionaries.
    """
    statement: CanonicalStatement
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence of the extraction (0 to 1)")
    parser_version: str = Field(..., description="Version of the specific parser used")
    warnings: List[str] = Field(default_factory=list, description="Any warnings encountered during extraction")

class BaseBankParser(ABC):
    """
    Abstract interface that all specific bank parsers MUST implement.
    Forbids returning dictionaries; mandates returning a ParserResult containing CanonicalStatement.
    """
    
    @abstractmethod
    def parse(self, raw_bytes: bytes, document_uuid: str) -> ParserResult:
        """
        Parses raw bank statement bytes and returns a standardized ParserResult.
        Raises:
            ParserConfidenceError: If the parser is not confident in the extraction.
            ParserValidationError: If the extracted data fails internal integrity checks.
        """
        pass
