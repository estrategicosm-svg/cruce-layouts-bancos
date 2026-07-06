import os
import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Tuple
from datetime import date, datetime
import uuid
import uuid_utils # Assuming uuid7 is available or just standard uuid
from xml.etree import ElementTree as ET
from decimal import Decimal


# ---------------------------------------------------------------------------
# Logger configuration
# ---------------------------------------------------------------------------
_logger = logging.getLogger("process_files")
_logger.setLevel(logging.DEBUG)

_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
_logger.addHandler(_ch)

_logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(_logs_dir, exist_ok=True)

_fh = logging.FileHandler(os.path.join(_logs_dir, "app.log"), encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
_logger.addHandler(_fh)

from infrastructure.database.uow import SQLAlchemyUnitOfWork
from infrastructure.database.orm import models
from domains.conciliation.engine import ConciliationEngine
from domains.conciliation.tolerance import ToleranceEngine
from domains.conciliation.strategies import (
    UUIDMatchStrategy,
    ReferenceMatchStrategy,
    SubsetSumMatchStrategy,
    ManyToOneMatchStrategy,
    SplitPaymentMatchStrategy
)
from domains.sat.validator import SATValidator
from domains.sat.rules.iva_rule import IVARule
from domains.sat.rules.cfdi_status_rule import CFDIStatusRule
from domains.accounting.engine import AccountingEngine
from domains.accounting.rules.egreso_rule import EgresoRule
from domains.accounting.rules.iva_acreditable_rule import IVAAcreditableRule
from domains.accounting.rules.proveedor_rule import ProveedorRule
from domains.accounting.rules.pago_rule import PagoRule
from domains.accounting.rules.ingreso_rule import IngresoRule
from domains.accounting.rules.iva_rule import IVARule as AccountingIVARule
from domains.configuration.engine import ConfigurationEngine
from domains.configuration.repositories import ConfigurationRepository
from domains.configuration.models import GeneralConfiguration, ConfigurationVersion, Tenant, AccountingConfiguration
from domains.shared.canonical_models import CanonicalTransaction as DomainTransaction
from domains.shared.canonical_models import CanonicalXML as DomainXML

@dataclass
class ProcessResult:
    """Resultado de una ejecución de ProcessFilesAndPersistUseCase.execute()."""
    run_id: str
    total_files: int = 0
    failed_files: int = 0
    failed_file_names: List[str] = field(default_factory=list)


class InMemoryConfigRepo(ConfigurationRepository):
    def __init__(self):
        self.globals = []
    def add_tenant(self, tenant: Tenant) -> None: pass
    def get_tenant(self, tenant_id: str) -> Tenant: return None
    def add_global_config(self, config: GeneralConfiguration) -> None: self.globals.append(config)
    def get_global_configs(self) -> List[GeneralConfiguration]: return self.globals
    def add_company_config(self, config) -> None: pass
    def get_company_configs(self, tenant_id: str) -> List: return []

class ProcessFilesAndPersistUseCase:
    def __init__(self, uow: SQLAlchemyUnitOfWork):
        self.uow = uow
        
        # Initialize engines
        repo = InMemoryConfigRepo()
        self.config_engine = ConfigurationEngine(repo)
        self.config_engine.register_global_config(GeneralConfiguration(
            id="GLOBAL_1",
            version_info=ConfigurationVersion(version="1.0"),
            accounting=AccountingConfiguration(
                cuenta_gastos="501-01-000",
                cuenta_compras="501-02-000",
                cuenta_activos="103-01-000",
                cuenta_iva_acreditable="118-01-000",
                cuenta_proveedores="201-01-000",
                cuenta_bancos="102-01-000"
            )
        ))
        
        self.accounting_engine = AccountingEngine(
            self.config_engine,
            rules=[
                EgresoRule(),
                IVAAcreditableRule(),
                ProveedorRule(),
                PagoRule(),
                IngresoRule(),
                AccountingIVARule()
            ]
        )
        
        tolerance = ToleranceEngine(Decimal("0.01"), 3)
        self.conciliation_engine = ConciliationEngine(strategies=[
            UUIDMatchStrategy(tolerance),
            ReferenceMatchStrategy(tolerance),
            SubsetSumMatchStrategy(tolerance),
            ManyToOneMatchStrategy(tolerance),
            SplitPaymentMatchStrategy(tolerance)
        ])
        
        self.sat_validator = SATValidator(rules=[IVARule(), CFDIStatusRule()])

    def _calculate_hash(self, file_path: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _parse_cfdi(self, file_path: str) -> DomainXML:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {'cfdi': 'http://www.sat.gob.mx/cfd/4', 'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'}
        if not root.findall('.//cfdi:Emisor', ns):
            ns['cfdi'] = 'http://www.sat.gob.mx/cfd/3'
        
        emisor = root.find('.//cfdi:Emisor', ns)
        receptor = root.find('.//cfdi:Receptor', ns)
        tfd = root.find('.//tfd:TimbreFiscalDigital', ns)
        
        rfc_emisor = emisor.attrib.get('Rfc', 'UNKNOWN') if emisor is not None else 'UNKNOWN'
        rfc_receptor = receptor.attrib.get('Rfc', 'UNKNOWN') if receptor is not None else 'UNKNOWN'
        tipo = root.attrib.get('TipoDeComprobante', 'I')
        subtotal = Decimal(root.attrib.get('SubTotal', '0.00'))
        total = Decimal(root.attrib.get('Total', '0.00'))
        uuid_cfdi = tfd.attrib.get('UUID', 'NO-UUID') if tfd is not None else 'NO-UUID'
        
        impuestos_desglosados = {"IVA": []}
        conceptos = root.findall('.//cfdi:Concepto', ns)
        for concepto in conceptos:
            traslados = concepto.findall('.//cfdi:Traslado', ns)
            for t in traslados:
                if t.attrib.get('Impuesto') == '002':
                    impuestos_desglosados["IVA"].append({
                        "TasaOCuota": t.attrib.get('TasaOCuota', '0.160000'),
                        "Importe": t.attrib.get('Importe', '0.00')
                    })
                    
        return DomainXML(
            uuid_cfdi=uuid_cfdi,
            rfc_emisor=rfc_emisor,
            rfc_receptor=rfc_receptor,
            tipo_cfdi=tipo,
            subtotal=subtotal,
            total=total,
            impuestos_desglosados=impuestos_desglosados
        )

    def execute(self, file_paths: List[str], tenant_id: str) -> ProcessResult:
        # Generate a unique processing run ID for traceablity
        run_id = str(uuid.uuid4())
        total_files = len(file_paths)
        failed_files: List[str] = []

        _logger.info("Processing run %s started | tenant=%s | files=%d", run_id, tenant_id, total_files)

        with self.uow as uow:
            # 1. Intake & Hash
            xmls_to_process = []

            company = uow.companies.get_by_rfc(tenant_id)
            if not company:
                company = models.Company(
                    id=str(uuid.uuid4()),
                    rfc=tenant_id,
                    razon_social="Tenant " + tenant_id,
                    processing_run_id=run_id
                )
                uow.companies.add(company)

            for path in file_paths:
                file_hash = self._calculate_hash(path)
                file_name = os.path.basename(path)
                file_size = os.path.getsize(path)

                # Check Idempotency
                existing_doc = uow.documents.get_by_hash(file_hash)

                if existing_doc:
                    # Same document, do not duplicate. Just use existing_doc.
                    doc_orm = existing_doc

                    # Log Workflow Event for reprocessing
                    uow.workflow_events.add(models.WorkflowEvent(
                        id=str(uuid.uuid4()),
                        document_id=doc_orm.id,
                        estado="REPROCESSED",
                        processing_run_id=run_id
                    ))
                else:
                    # New Document
                    doc_id = str(uuid.uuid4())
                    tipo = "XML" if path.lower().endswith(".xml") else "PDF"

                    doc_orm = models.Document(
                        id=doc_id,
                        company_id=company.id,
                        hash_sha256=file_hash,
                        tipo=tipo,
                        tamanio_bytes=file_size,
                        processing_run_id=run_id,
                        estado_workflow="RECEIVED",
                        version=1
                    )
                    uow.documents.add(doc_orm)

                    doc_version = models.DocumentVersion(
                        id=str(uuid.uuid4()),
                        document_id=doc_id,
                        storage_url=path,
                        version_number=1,
                        processing_run_id=run_id
                    )
                    uow.documents.add_version(doc_version)

                    uow.workflow_events.add(models.WorkflowEvent(
                        id=str(uuid.uuid4()),
                        document_id=doc_id,
                        estado="RECEIVED",
                        processing_run_id=run_id
                    ))

                if path.lower().endswith(".xml"):
                    try:
                        domain_xml = self._parse_cfdi(path)
                        xmls_to_process.append((doc_orm, domain_xml))
                    except Exception as exc:
                        _logger.exception(
                            "XML parse error | run=%s file=%s tipo=%s",
                            run_id, file_name, type(exc).__name__,
                        )
                        doc_orm.estado_workflow = "FAILED"
                        doc_orm.status = "ERROR"
                        uow.workflow_events.add(models.WorkflowEvent(
                            id=str(uuid.uuid4()),
                            document_id=doc_orm.id,
                            estado="FAILED",
                            processing_run_id=run_id,
                            mensaje=f"Parse error: {exc}"
                        ))
                        failed_files.append(file_name)
                elif path.lower().endswith(".pdf"):
                    _logger.debug("PDF stub skipped | run=%s file=%s", run_id, file_name)
                    pass
            
            # 2. SAT Engine & XML Persist
            domain_xmls = []
            for doc_orm, domain_xml in xmls_to_process:
                # SAT Validation
                sat_res = self.sat_validator.validate(domain_xml)
                
                # Persist CanonicalXML
                xml_orm = uow.xmls.get_by_uuid(domain_xml.uuid_cfdi)
                if xml_orm:
                    xml_orm.version += 1
                    xml_orm.processing_run_id = run_id
                else:
                    xml_orm = models.CanonicalXML(
                        id=str(uuid.uuid4()),
                        document_uuid=doc_orm.id,
                        uuid_cfdi=domain_xml.uuid_cfdi,
                        rfc_emisor=domain_xml.rfc_emisor,
                        rfc_receptor=domain_xml.rfc_receptor,
                        tipo_cfdi=domain_xml.tipo_cfdi,
                        subtotal=domain_xml.subtotal,
                        total=domain_xml.total,
                        processing_run_id=run_id,
                        version=1
                    )
                    uow.xmls.add(xml_orm)
                
                # Persist SAT Result
                sat_orm = models.SATValidationResult(
                    id=str(uuid.uuid4()),
                    xml_uuid=xml_orm.id,
                    overall_status=sat_res.overall_status.value,
                    rule_results=[r.model_dump(mode="json") for r in sat_res.results],
                    processing_run_id=run_id,
                    version=xml_orm.version
                )
                uow.sat_results.add(sat_orm)
                
                domain_xmls.append(domain_xml)
            
            # 3. Accounting Engine
            for doc_orm, domain_xml in xmls_to_process:
                proposal = self.accounting_engine.generate_proposal(tenant_id, date.today(), xml=domain_xml)
                acct_orm = models.AccountingProposal(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    source_type="XML",
                    source_uuid=domain_xml.uuid_cfdi,
                    fecha=proposal.fecha,
                    es_cuadrada=(proposal.total_cargos == proposal.total_abonos),
                    total_cargos=proposal.total_cargos,
                    total_abonos=proposal.total_abonos,
                    asientos=[a.model_dump(mode="json") for a in proposal.entries],
                    processing_run_id=run_id
                )
                uow.accounting.add(acct_orm)
            
            # 4. Conciliation Engine
            if domain_xmls:
                concil_res = self.conciliation_engine.conciliate([], domain_xmls) # No TX for now
                
                concil_orm = models.ConciliationResult(
                    id=str(uuid.uuid4()),
                    total_transactions_analyzed=0,
                    total_xmls_analyzed=len(domain_xmls),
                    exact_matches_count=len(concil_res.matches),
                    partial_matches_count=0,
                    unmatched_transactions=[],
                    unmatched_xmls=[x.uuid_cfdi for x in concil_res.unmatched_xmls],
                    processing_run_id=run_id
                )
                uow.conciliation.add_result(concil_orm)
                
                for match in concil_res.matches:
                    match_orm = models.MatchCandidate(
                        id=str(uuid.uuid4()),
                        conciliation_result_id=concil_orm.id,
                        status=match.status.value,
                        strategy_used=match.strategy_used,
                        confidence=match.confidence,
                        transaction_ids=[t.uuid for t in match.transactions],
                        xml_ids=[x.uuid_cfdi for x in match.xmls],
                        explanations=[e.model_dump(mode="json") for e in match.explanations],
                        processing_run_id=run_id
                    )
                    uow.conciliation.add_match(match_orm)
            
            # 5. Commit
            uow.commit()

        result = ProcessResult(
            run_id=run_id,
            total_files=total_files,
            failed_files=len(failed_files),
            failed_file_names=failed_files,
        )

        if result.failed_files == result.total_files:
            _logger.warning(
                "All files failed for run %s | total=%d | files=%s",
                run_id, total_files, failed_files,
            )
        elif result.failed_files > 0:
            _logger.info(
                "Partial failures for run %s | ok=%d failed=%d",
                run_id, total_files - result.failed_files, result.failed_files,
            )
        else:
            _logger.info("Run %s completed successfully | files=%d", run_id, total_files)

        return result
