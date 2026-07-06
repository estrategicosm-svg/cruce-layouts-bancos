from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import List

from domains.shared.canonical_models import CanonicalXML

class CFDIParserResult(BaseModel):
    """
    Standard result returned by the CFDI parser.
    Ensures that the output is always a CanonicalXML,
    not raw dictionaries.
    """
    xml: CanonicalXML
    warnings: List[str] = Field(default_factory=list, description="Any warnings encountered during extraction")

class BaseCFDIParser(ABC):
    """
    Abstract interface that CFDI parsers MUST implement.
    Forbids returning dictionaries; mandates returning a CFDIParserResult containing CanonicalXML.
    """
    
    @abstractmethod
    def parse(self, raw_bytes: bytes) -> CFDIParserResult:
        """
        Parses raw XML bytes and returns a standardized CFDIParserResult.
        Raises:
            CFDIParseError: If the XML is malformed.
            CFDIValidationError: If the XML lacks mandatory nodes/attributes.
            UnsupportedCFDITypeError: If the type is not supported.
        """
        pass
