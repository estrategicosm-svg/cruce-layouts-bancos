from abc import ABC, abstractmethod
from typing import Any
from domains.shared.canonical_models import CanonicalStatement, CanonicalXML

class BaseNormalizer(ABC):
    """
    Abstract interface for all normalizers.
    Ensures that raw/parsed data is transformed into validated canonical models.
    """
    @abstractmethod
    def normalize(self, raw_data: Any) -> Any:
        pass

class BankStatementNormalizer(BaseNormalizer):
    """
    Interface for normalizing raw banking parser outputs into a validated CanonicalStatement.
    """
    @abstractmethod
    def normalize(self, raw_data: dict) -> CanonicalStatement:
        """
        Expects a raw dictionary (or intermediate structure) from a parser and 
        returns a fully validated CanonicalStatement.
        """
        pass

class CFDINormalizer(BaseNormalizer):
    """
    Interface for normalizing raw CFDI XML parser outputs into a validated CanonicalXML.
    """
    @abstractmethod
    def normalize(self, raw_data: dict) -> CanonicalXML:
        """
        Expects a raw dictionary (or intermediate structure) from an XML parser 
        and returns a fully validated CanonicalXML.
        """
        pass
