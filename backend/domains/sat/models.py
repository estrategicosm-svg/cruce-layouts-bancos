from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional

class SATRuleStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"

class SATRuleSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class SATRuleResult(BaseModel):
    rule_name: str
    version: str = "1.0"
    status: SATRuleStatus
    severity: SATRuleSeverity
    explanation: str
    details: dict = Field(default_factory=dict)

class SATValidationResult(BaseModel):
    uuid_cfdi: str
    overall_status: SATRuleStatus
    results: List[SATRuleResult] = Field(default_factory=list)
