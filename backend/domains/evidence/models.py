from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class EvidenceType(str, Enum):
    ESTADO_CUENTA = "ESTADO_CUENTA"
    XML_CFDI = "XML_CFDI"
    PDF_REPRESENTACION = "PDF_REPRESENTACION"
    DOCUMENTO_ORIGINAL = "DOCUMENTO_ORIGINAL"
    TRANSACCION_BANCARIA = "TRANSACCION_BANCARIA"
    RESULTADO_SAT = "RESULTADO_SAT"
    MATCH_CONCILIACION = "MATCH_CONCILIACION"
    WORKFLOW = "WORKFLOW"
    HASH_DOCUMENTAL = "HASH_DOCUMENTAL"

class EvidenceStatus(str, Enum):
    DRAFT = "DRAFT"
    SEALED = "SEALED"
    INVALIDATED = "INVALIDATED"

class EvidenceReference(BaseModel):
    """
    A cross-reference to another entity in the system by UUID.
    """
    target_uuid: str
    target_type: str  # e.g., 'DOCUMENT', 'TRANSACTION', 'XML', 'MATCH'
    description: str

class EvidenceItem(BaseModel):
    """
    A single piece of evidence inside a package.
    """
    item_id: str
    evidence_type: EvidenceType
    content: dict  # Serialized deterministic content
    references: List[EvidenceReference] = Field(default_factory=list)

class EvidencePackage(BaseModel):
    """
    The main Evidence container. Completely deterministic and immutable once SEALED.
    """
    package_uuid: str
    document_uuid: str
    empresa_id: str
    sha256: str
    fingerprint: str
    fecha_creacion: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1
    status: EvidenceStatus = EvidenceStatus.DRAFT
    
    items: List[EvidenceItem] = Field(default_factory=list)
    workflow_history: List[dict] = Field(default_factory=list) # Snapshot of workflow

    def validate_integrity(self):
        if not self.document_uuid:
            raise ValueError("Evidence package must be bound to a Document UUID.")
        if not self.sha256 or not self.fingerprint:
            raise ValueError("Evidence package must contain document hashes for integrity.")
        if not self.workflow_history:
            raise ValueError("Evidence package must contain the document's workflow history.")
            
        for item in self.items:
            for ref in item.references:
                if not ref.target_uuid:
                    raise ValueError(f"Orphan reference found in item {item.item_id}")
