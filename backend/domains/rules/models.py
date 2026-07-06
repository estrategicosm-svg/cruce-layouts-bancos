from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import date, datetime
from domains.shared.canonical_models import CanonicalDocument, CanonicalTransaction, CanonicalXML

class RuleType(str, Enum):
    SAT = "SAT"
    ACCOUNTING = "ACCOUNTING"
    CONCILIATION = "CONCILIATION"
    DOCUMENT = "DOCUMENT"
    VALIDATION = "VALIDATION"
    WORKFLOW = "WORKFLOW"
    REPORTING = "REPORTING"

class RuleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DEPRECATED = "DEPRECATED"

class RulePriority(int, Enum):
    LOW = 10
    MEDIUM = 50
    HIGH = 100
    CRITICAL = 1000

class RuleScope(BaseModel):
    empresa_rfc: Optional[str] = None
    ejercicio: Optional[int] = None
    periodo: Optional[int] = None

class RuleVersion(BaseModel):
    version: str
    fecha_inicio: date
    fecha_fin: Optional[date] = None

class Rule(BaseModel):
    id: str
    name: str
    description: str
    rule_type: RuleType
    version_info: RuleVersion
    status: RuleStatus = RuleStatus.ACTIVE
    priority: RulePriority = RulePriority.MEDIUM
    scope: RuleScope = Field(default_factory=RuleScope)
    config: Dict[str, Any] = Field(default_factory=dict)

class RuleContext(BaseModel):
    """
    Context carrier passed into rules.
    """
    document: Optional[CanonicalDocument] = None
    transaction: Optional[CanonicalTransaction] = None
    xml: Optional[CanonicalXML] = None
    workflow: Optional[List[dict]] = None
    evidence_package: Optional[dict] = None
    global_config: Dict[str, Any] = Field(default_factory=dict)

class RuleResult(BaseModel):
    rule_id: str
    passed: bool
    message: str
    details: dict = Field(default_factory=dict)
