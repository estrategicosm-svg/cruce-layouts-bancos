from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field

class CanonicalDocument(BaseModel):
    uuid: str = Field(..., description="UUIDv7 of the document")
    empresa_rfc: str = Field(..., description="RFC of the company that owns the document")
    hash_sha256: str = Field(..., description="SHA-256 hash for integrity and uniqueness")
    tipo: str = Field(..., description="Document type (e.g., PDF_STATEMENT, XML_CFDI)")
    tamanio_bytes: int = Field(..., description="Size in bytes")
    fecha_carga: datetime = Field(default_factory=datetime.utcnow)
    estado_workflow: str = Field(default="RECIBIDO")

class CanonicalTransaction(BaseModel):
    uuid: str = Field(..., description="UUIDv7 of the transaction")
    statement_uuid: str = Field(..., description="UUID of the parent statement")
    fecha_operacion: date = Field(..., description="Date of the operation")
    monto_absoluto: Decimal = Field(..., description="Absolute amount of the transaction", ge=0)
    naturaleza: str = Field(..., description="CARGO or ABONO")
    moneda: str = Field(default="MXN", description="Currency (e.g., MXN, USD)")
    concepto_original: str = Field(..., description="Raw concept from the bank (formerly concepto_bancario_original)")
    referencia_bancaria_original: Optional[str] = Field(None, description="Raw reference column/field from the bank if separated")
    referencia_bancaria_limpia: Optional[str] = Field(None, description="Cleaned numerical reference")
    clave_rastreo: Optional[str] = Field(None, description="Clave de Rastreo (SPEI/CEP)")
    numero_operacion: Optional[str] = Field(None, description="Operacion / Transaccion / Folio / Dojcto number")
    autorizacion: Optional[str] = Field(None, description="Authorization number (AUT)")

class CanonicalStatement(BaseModel):
    document_uuid: str = Field(..., description="UUID of the source document")
    banco: str = Field(..., description="Bank name (e.g., BBVA, BANAMEX)")
    cuenta: str = Field(..., description="Account number or identifier")
    periodo_inicio: date = Field(...)
    periodo_fin: date = Field(...)
    moneda: str = Field(default="MXN")
    saldo_inicial: Decimal = Field(...)
    saldo_final: Decimal = Field(...)
    transacciones: List[CanonicalTransaction] = Field(default_factory=list)

class CanonicalXML(BaseModel):
    uuid_cfdi: str = Field(..., description="SAT UUID")
    rfc_emisor: str = Field(...)
    rfc_receptor: str = Field(...)
    tipo_cfdi: str = Field(..., description="I, E, P, N, T")
    metodo_pago: Optional[str] = Field(None, description="PUE or PPD")
    forma_pago: Optional[str] = Field(None)
    subtotal: Decimal = Field(...)
    impuestos_desglosados: dict = Field(default_factory=dict)
    total: Decimal = Field(...)
    estado_cancelacion: str = Field(default="VIGENTE")

class CanonicalEvidence(BaseModel):
    uuid: str = Field(..., description="UUIDv7 of the evidence package")
    match_uuid: str = Field(..., description="UUID of the conciliation match")
    urls_adjuntos: List[str] = Field(default_factory=list, description="List of storage URLs")
    trazabilidad_log: str = Field(..., description="Human readable explanation of the match")
