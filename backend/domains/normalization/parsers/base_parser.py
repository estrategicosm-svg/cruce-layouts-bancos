from abc import ABC, abstractmethod
from typing import List, Optional
from decimal import Decimal

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from domains.shared.canonical_models import CanonicalStatement, CanonicalTransaction

class ParseError(Exception):
    """Raised when a parser fails to parse a document."""
    pass

class MathIntegrityError(ParseError):
    """Raised when the mathematical integrity of a statement is invalid (e.g. balances don't match transactions)."""
    pass

class BaseBankParser(ABC):
    """Base interface for all real bank parsers in Phase 18."""
    
    @abstractmethod
    def parse(self, filepath: str, document_uuid: str) -> CanonicalStatement:
        """
        Parses a bank statement PDF and returns a strictly normalized CanonicalStatement.
        
        Args:
            filepath: Path to the real PDF file.
            document_uuid: UUID of the source document for traceability.
            
        Returns:
            CanonicalStatement
            
        Raises:
            ParseError: If parsing fails.
            MathIntegrityError: If the statement does not square mathematically.
        """
        pass
    
    def validate_math_integrity(self, statement: CanonicalStatement) -> None:
        """
        Validates that: Initial Balance + Total Credits - Total Debits = Final Balance
        Allows for a small floating point / decimal rounding tolerance (e.g., 0.05).
        """
        saldo_calculado = statement.saldo_inicial
        
        cargos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "CARGO")
        abonos = sum(tx.monto_absoluto for tx in statement.transacciones if tx.naturaleza == "ABONO")
        
        saldo_calculado += abonos
        saldo_calculado -= cargos
        
        diff = abs(saldo_calculado - statement.saldo_final)
        
        if diff > Decimal("0.05"):
            raise MathIntegrityError(
                f"Cuadre matemático fallido para cuenta {statement.cuenta}. "
                f"Inicial: {statement.saldo_inicial}, Cargos: {cargos}, Abonos: {abonos}. "
                f"Saldo Final Calculado: {saldo_calculado}. Saldo Final Reportado: {statement.saldo_final}."
            )
