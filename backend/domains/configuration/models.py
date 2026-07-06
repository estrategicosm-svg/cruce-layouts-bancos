from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class Tenant(BaseModel):
    id: str
    rfc: str
    razon_social: str
    is_active: bool = True

class AccountingConfiguration(BaseModel):
    catalogo_contable_id: Optional[str] = None
    reglas_activas: List[str] = Field(default_factory=list)
    cuenta_gastos: Optional[str] = None
    cuenta_compras: Optional[str] = None
    cuenta_activos: Optional[str] = None
    cuenta_iva_acreditable: Optional[str] = None
    cuenta_proveedores: Optional[str] = None
    cuenta_bancos: Optional[str] = None

class SATConfiguration(BaseModel):
    reglas_activas: List[str] = Field(default_factory=list)

class ConciliationConfiguration(BaseModel):
    bancos_activos: List[str] = Field(default_factory=list)
    monedas: List[str] = Field(default=["MXN", "USD"])
    tolerancia_dias: int = 0
    tolerancia_centavos: float = 0.0

class WorkflowConfiguration(BaseModel):
    auto_advance: bool = True

class StorageConfiguration(BaseModel):
    provider: str = "LOCAL"

class RuleConfiguration(BaseModel):
    strict_mode: bool = True

class ReportConfiguration(BaseModel):
    formato_default: str = "PDF"

class ConfigurationVersion(BaseModel):
    version: str
    fecha_creacion: datetime = Field(default_factory=datetime.utcnow)
    activo: bool = True

class GeneralConfiguration(BaseModel):
    """Fallback Global Config"""
    id: str
    version_info: ConfigurationVersion
    accounting: AccountingConfiguration = Field(default_factory=AccountingConfiguration)
    sat: SATConfiguration = Field(default_factory=SATConfiguration)
    conciliation: ConciliationConfiguration = Field(default_factory=ConciliationConfiguration)
    workflow: WorkflowConfiguration = Field(default_factory=WorkflowConfiguration)
    storage: StorageConfiguration = Field(default_factory=StorageConfiguration)
    rule: RuleConfiguration = Field(default_factory=RuleConfiguration)
    report: ReportConfiguration = Field(default_factory=ReportConfiguration)

class CompanyConfiguration(GeneralConfiguration):
    """Tenant-specific config, can override global."""
    tenant_id: str
    ejercicio: Optional[int] = None
    periodo: Optional[int] = None
