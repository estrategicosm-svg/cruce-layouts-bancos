from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List
from domains.shared.canonical_models import CanonicalTransaction, CanonicalXML

class MatchStatus(str, Enum):
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    CONFLICT = "CONFLICT"
    UNMATCHED = "UNMATCHED"

class MatchExplanation(BaseModel):
    """
    Human-readable deterministic explanation of why a match succeeded or failed.
    """
    rule_name: str
    description: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    details: dict = Field(default_factory=dict)

class MatchCandidate(BaseModel):
    """
    A proposed link between transaction(s) and XML(s).
    """
    # Para M:N, 1:N, N:1
    transactions: List[CanonicalTransaction] = Field(default_factory=list)
    xmls: List[CanonicalXML] = Field(default_factory=list)
    
    # Optional fields for partials
    partial_applied_amount: Optional[float] = None
    partial_remaining_amount: Optional[float] = None

    status: MatchStatus
    explanations: List[MatchExplanation] = Field(default_factory=list)
    
    # Priority and confidence
    strategy_used: str = "UNKNOWN"
    rules_applied: List[str] = Field(default_factory=list)
    confidence: float = 0.0

class MatchResult(BaseModel):
    """
    Final result of the conciliation engine for a given set of data.
    """
    matches: List[MatchCandidate] = Field(default_factory=list)
    unmatched_transactions: List[CanonicalTransaction] = Field(default_factory=list)
    unmatched_xmls: List[CanonicalXML] = Field(default_factory=list)
