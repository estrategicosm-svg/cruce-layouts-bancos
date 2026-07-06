from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from enum import Enum
from datetime import datetime

class AuditSection(str, Enum):
    CARATULA = "CARATULA"
    RESUMEN = "RESUMEN"
    DOCUMENTOS = "DOCUMENTOS"
    ESTADOS_CUENTA = "ESTADOS_CUENTA"
    CFDI = "CFDI"
    CONCILIACION = "CONCILIACION"
    VALIDACIONES_SAT = "VALIDACIONES_SAT"
    POLIZAS = "POLIZAS"
    EVIDENCIAS = "EVIDENCIAS"
    WORKFLOW = "WORKFLOW"
    OBSERVACIONES = "OBSERVACIONES"

class AuditObservationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

class AuditObservation(BaseModel):
    section: AuditSection
    severity: AuditObservationSeverity
    message: str
    item_id: Optional[str] = None
    
class AuditAttachment(BaseModel):
    id: str
    type: str
    storage_url: str
    version: int
    hash_sha256: str
    
class AuditSummary(BaseModel):
    tenant_id: str
    processing_run_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    periodo: Optional[str] = None
    ejercicio: Optional[str] = None
    
class AuditMetrics(BaseModel):
    total_documentos: int = 0
    total_xmls: int = 0
    total_transacciones_bancarias: int = 0
    total_polizas_cuadradas: int = 0
    total_polizas_rechazadas: int = 0
    cfdis_cancelados: int = 0
    cfdis_con_errores_validacion: int = 0
    xmls_sin_conciliar: int = 0
    transacciones_sin_conciliar: int = 0
    matches_exactos: int = 0
    
class AuditIndexEntry(BaseModel):
    section: AuditSection
    title: str
    item_count: int

class AuditIndex(BaseModel):
    entries: List[AuditIndexEntry] = Field(default_factory=list)

class AuditFile(BaseModel):
    """
    Entidad Raíz del Expediente Electrónico SAT.
    Agrupa toda la información persistida, ensamblándola sin recalcular nada.
    """
    summary: AuditSummary
    metrics: AuditMetrics
    index: AuditIndex
    
    # Contenido detallado
    documentos: List[AuditAttachment] = Field(default_factory=list)
    xmls_raw: List[Dict[str, Any]] = Field(default_factory=list)
    transacciones_bancarias_raw: List[Dict[str, Any]] = Field(default_factory=list)
    resultados_sat: List[Dict[str, Any]] = Field(default_factory=list)
    resultados_conciliacion: List[Dict[str, Any]] = Field(default_factory=list)
    polizas: List[Dict[str, Any]] = Field(default_factory=list)
    eventos_workflow: List[Dict[str, Any]] = Field(default_factory=list)
    
    observaciones: List[AuditObservation] = Field(default_factory=list)
    
    def to_json(self) -> str:
        return self.model_dump_json(indent=2)
