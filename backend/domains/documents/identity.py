import hashlib
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime

class DocumentIdentity(BaseModel):
    """
    Core identity model for any document in the system.
    Serves as the master index containing deterministic properties.
    """
    document_uuid: str
    sha256: str
    empresa_id: str
    empresa_rfc: str
    ejercicio: int
    periodo: int
    tipo_documento: str
    subtipo_documento: Optional[str] = None
    banco: Optional[str] = None
    cuenta: Optional[str] = None
    moneda: str = "MXN"
    fecha_documento: date
    fecha_carga: datetime = Field(default_factory=datetime.utcnow)
    origen: str
    version: int = 1
    estado_workflow: str = "RECEIVED"

class Fingerprint:
    """
    Generates a deterministic unique hash combining structural metadata 
    to detect duplicates across the platform rapidly.
    """
    @staticmethod
    def generate(sha256: str, tamanio_bytes: int, fecha_documento: date, empresa_rfc: str, tipo_documento: str) -> str:
        # Example pattern: SHA256|TAMANIO|YYYY-MM-DD|RFC|TIPO
        raw_fingerprint = f"{sha256}|{tamanio_bytes}|{fecha_documento.isoformat()}|{empresa_rfc}|{tipo_documento}"
        return hashlib.sha256(raw_fingerprint.encode('utf-8')).hexdigest()
