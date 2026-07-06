from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date
from decimal import Decimal

class AccountingEntryType(str, Enum):
    CARGO = "CARGO"
    ABONO = "ABONO"

class AccountingProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    POSTED = "POSTED"

class AccountingEntry(BaseModel):
    cuenta_contable: str
    tipo: AccountingEntryType
    monto: Decimal
    concepto: str
    referencia: Optional[str] = None
    
class AccountingRuleResult(BaseModel):
    rule_name: str
    applied: bool
    entries: List[AccountingEntry] = Field(default_factory=list)
    explanation: str

class AccountingProposal(BaseModel):
    id: str
    tenant_id: str
    fecha: date
    moneda: str = "MXN"
    status: AccountingProposalStatus = AccountingProposalStatus.DRAFT
    document_uuid: Optional[str] = None
    transaction_uuid: Optional[str] = None
    xml_uuid: Optional[str] = None
    
    entries: List[AccountingEntry] = Field(default_factory=list)
    rule_results: List[AccountingRuleResult] = Field(default_factory=list)
    
    @property
    def total_cargos(self) -> Decimal:
        return sum((e.monto for e in self.entries if e.tipo == AccountingEntryType.CARGO), Decimal("0.0"))
        
    @property
    def total_abonos(self) -> Decimal:
        return sum((e.monto for e in self.entries if e.tipo == AccountingEntryType.ABONO), Decimal("0.0"))
