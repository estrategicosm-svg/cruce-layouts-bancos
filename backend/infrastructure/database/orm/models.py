from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Numeric, Date, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from infrastructure.database.orm.base import Base, AuditableMixin

class Company(Base, AuditableMixin):
    __tablename__ = "companies"
    
    id = Column(String, primary_key=True)  # UUIDv7
    rfc = Column(String(13), unique=True, nullable=False, index=True)
    razon_social = Column(String, nullable=False)
    
    documents = relationship("Document", back_populates="company")

class Document(Base, AuditableMixin):
    __tablename__ = "documents"
    
    id = Column(String, primary_key=True)  # UUIDv7
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    hash_sha256 = Column(String(64), unique=True, nullable=False, index=True)
    fingerprint = Column(String(64), unique=True, nullable=True, index=True)
    tipo = Column(String, nullable=False, index=True)
    subtipo_documento = Column(String, nullable=True)
    tamanio_bytes = Column(Integer, nullable=False)
    fecha_carga = Column(DateTime, default=datetime.utcnow, nullable=False)
    fecha_documento = Column(Date, nullable=True, index=True)
    ejercicio = Column(Integer, nullable=True, index=True)
    periodo = Column(Integer, nullable=True, index=True)
    banco = Column(String, nullable=True, index=True)
    cuenta = Column(String, nullable=True, index=True)
    moneda = Column(String(3), nullable=True, default="MXN")
    origen = Column(String, nullable=True)
    estado_workflow = Column(String, nullable=False, default="RECEIVED", index=True)
    uuid_cfdi = Column(String, nullable=True, index=True)
    referencia_bancaria = Column(String, nullable=True, index=True)
    
    company = relationship("Company", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document")
    workflow_events = relationship("WorkflowEvent", back_populates="document")
    canonical_statements = relationship("CanonicalStatement", back_populates="document")
    canonical_xmls = relationship("CanonicalXML", back_populates="document")

class DocumentVersion(Base, AuditableMixin):
    __tablename__ = "document_versions"
    
    id = Column(String, primary_key=True)  # UUIDv7
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    storage_url = Column(String, nullable=False)
    version_number = Column(Integer, nullable=False, default=1)
    fecha_version = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    document = relationship("Document", back_populates="versions")

class CanonicalStatement(Base, AuditableMixin):
    __tablename__ = "canonical_statements"
    
    id = Column(String, primary_key=True)
    document_uuid = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    banco = Column(String, nullable=False)
    cuenta = Column(String, nullable=False)
    periodo_inicio = Column(Date, nullable=False)
    periodo_fin = Column(Date, nullable=False)
    fecha_corte = Column(Date, nullable=True)
    moneda = Column(String(3), nullable=False, default="MXN")
    saldo_inicial = Column(Numeric(15, 2), nullable=False)
    saldo_final = Column(Numeric(15, 2), nullable=False)
    
    document = relationship("Document", back_populates="canonical_statements")
    transactions = relationship("CanonicalTransaction", back_populates="statement")

class CanonicalTransaction(Base, AuditableMixin):
    __tablename__ = "canonical_transactions"
    
    id = Column(String, primary_key=True)  # UUIDv7
    statement_uuid = Column(String, ForeignKey("canonical_statements.id"), nullable=False, index=True)
    fecha_operacion = Column(Date, nullable=False)
    monto_absoluto = Column(Numeric(15, 2), nullable=False)
    naturaleza = Column(String(10), nullable=False) # CARGO/ABONO
    moneda = Column(String(3), nullable=False, default="MXN")
    
    concepto_original = Column(String, nullable=False)
    referencia_bancaria_original = Column(String, nullable=True)
    referencia_bancaria_limpia = Column(String, nullable=True)
    clave_rastreo = Column(String, nullable=True)
    numero_operacion = Column(String, nullable=True)
    autorizacion = Column(String, nullable=True)
    
    statement = relationship("CanonicalStatement", back_populates="transactions")

class CanonicalXML(Base, AuditableMixin):
    __tablename__ = "canonical_xmls"
    
    id = Column(String, primary_key=True)  # UUIDv7 CFDI UUID
    document_uuid = Column(String, ForeignKey("documents.id"), nullable=True, index=True)
    uuid_cfdi = Column(String, nullable=False, index=True, unique=True)
    rfc_emisor = Column(String(13), nullable=False, index=True)
    rfc_receptor = Column(String(13), nullable=False, index=True)
    tipo_cfdi = Column(String(2), nullable=False)
    metodo_pago = Column(String(3), nullable=True)
    forma_pago = Column(String(3), nullable=True)
    subtotal = Column(Numeric(15, 2), nullable=False)
    total = Column(Numeric(15, 2), nullable=False)
    estado_cancelacion = Column(String, nullable=False, default="VIGENTE")
    impuestos_desglosados = Column(JSON, nullable=True)
    
    document = relationship("Document", back_populates="canonical_xmls")
    sat_results = relationship("SATValidationResult", back_populates="xml")

class SATValidationResult(Base, AuditableMixin):
    __tablename__ = "sat_validation_results"
    
    id = Column(String, primary_key=True)
    xml_uuid = Column(String, ForeignKey("canonical_xmls.id"), nullable=False, index=True)
    overall_status = Column(String, nullable=False)
    rule_results = Column(JSON, nullable=True)
    
    xml = relationship("CanonicalXML", back_populates="sat_results")

class AccountingProposal(Base, AuditableMixin):
    __tablename__ = "accounting_proposals"
    
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    source_type = Column(String, nullable=False) # XML, TX, etc.
    source_uuid = Column(String, nullable=False, index=True)
    fecha = Column(Date, nullable=False)
    es_cuadrada = Column(Boolean, nullable=False)
    total_cargos = Column(Numeric(15, 2), nullable=False)
    total_abonos = Column(Numeric(15, 2), nullable=False)
    asientos = Column(JSON, nullable=False)
    tipo_poliza = Column(String, nullable=False, default="DIARIO")

class ConciliationResult(Base, AuditableMixin):
    __tablename__ = "conciliation_results"
    
    id = Column(String, primary_key=True)
    run_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    total_transactions_analyzed = Column(Integer, nullable=False)
    total_xmls_analyzed = Column(Integer, nullable=False)
    exact_matches_count = Column(Integer, nullable=False)
    partial_matches_count = Column(Integer, nullable=False)
    unmatched_transactions = Column(JSON, nullable=False)
    unmatched_xmls = Column(JSON, nullable=False)
    
    matches = relationship("MatchCandidate", back_populates="result")

class MatchCandidate(Base, AuditableMixin):
    __tablename__ = "match_candidates"
    
    id = Column(String, primary_key=True)
    conciliation_result_id = Column(String, ForeignKey("conciliation_results.id"), nullable=False)
    status = Column(String, nullable=False) # EXACT, PARTIAL, MANUAL
    strategy_used = Column(String, nullable=False)
    confidence = Column(Numeric(5, 4), nullable=False)
    partial_applied_amount = Column(Numeric(15, 2), nullable=True)
    partial_remaining_amount = Column(Numeric(15, 2), nullable=True)
    
    # Store IDs of related transactions and XMLs as JSON array
    transaction_ids = Column(JSON, nullable=False)
    xml_ids = Column(JSON, nullable=False)
    
    explanations = Column(JSON, nullable=True)
    
    result = relationship("ConciliationResult", back_populates="matches")

class EvidencePackage(Base, AuditableMixin):
    __tablename__ = "evidence_packages"
    
    id = Column(String, primary_key=True)
    match_candidate_id = Column(String, ForeignKey("match_candidates.id"), nullable=False)
    storage_url = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    is_compressed = Column(Boolean, nullable=False, default=True)

class WorkflowEvent(Base, AuditableMixin):
    __tablename__ = "workflow_events"
    
    id = Column(String, primary_key=True)  # UUIDv7
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    estado = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    mensaje = Column(String, nullable=True)
    
    document = relationship("Document", back_populates="workflow_events")
