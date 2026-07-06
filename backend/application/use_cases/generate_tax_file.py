from typing import List, Optional
from datetime import datetime
import json

from infrastructure.database.uow import SQLAlchemyUnitOfWork
from domains.reporting.models import (
    AuditFile, AuditSummary, AuditMetrics, AuditIndex, AuditIndexEntry,
    AuditSection, AuditAttachment, AuditObservation, AuditObservationSeverity
)

class GenerateTaxFileUseCase:
    def __init__(self, uow: SQLAlchemyUnitOfWork):
        self.uow = uow

    def execute(self, processing_run_id: str) -> AuditFile:
        with self.uow as uow:
            # 1. Recuperar información
            docs = uow.documents.get_all_by_run_id(processing_run_id)
            xmls = uow.xmls.get_all_by_run_id(processing_run_id)
            sat_results = uow.sat_results.get_all_by_run_id(processing_run_id)
            proposals = uow.accounting.get_all_by_run_id(processing_run_id)
            conciliation = uow.conciliation.get_result_by_run_id(processing_run_id)
            workflow = uow.workflow_events.get_all_by_run_id(processing_run_id)
            
            # Por ahora asumo el tenant_id de las propuestas o de los xmls
            tenant_id = "UNKNOWN"
            if proposals:
                tenant_id = proposals[0].tenant_id
            elif xmls:
                tenant_id = xmls[0].rfc_receptor

            # 2. Inicializar Métricas y Observaciones
            metrics = AuditMetrics()
            observaciones: List[AuditObservation] = []
            
            # Documentos
            metrics.total_documentos = len(docs)
            attachments = []
            for d in docs:
                version_orm = uow.documents.get_latest_version(d.id)
                attachments.append(AuditAttachment(
                    id=d.id,
                    type=d.tipo,
                    storage_url=version_orm.storage_url if version_orm else "MISSING",
                    version=d.version,
                    hash_sha256=d.hash_sha256
                ))
            
            if not docs:
                observaciones.append(AuditObservation(
                    section=AuditSection.DOCUMENTOS,
                    severity=AuditObservationSeverity.CRITICAL,
                    message="No se encontraron documentos para el run_id proporcionado."
                ))

            # XMLs y SAT
            metrics.total_xmls = len(xmls)
            xmls_raw = []
            for x in xmls:
                xmls_raw.append({
                    "id": x.id,
                    "uuid_cfdi": x.uuid_cfdi,
                    "rfc_emisor": x.rfc_emisor,
                    "rfc_receptor": x.rfc_receptor,
                    "total": str(x.total) if x.total else None
                })
            
            sat_raw = []
            for sr in sat_results:
                sat_raw.append({
                    "xml_uuid": sr.xml_uuid,
                    "overall_status": sr.overall_status
                })
                if sr.overall_status == "FAIL" or sr.overall_status == "REJECTED": # Check exactly the string
                    metrics.cfdis_cancelados += 1
                    observaciones.append(AuditObservation(
                        section=AuditSection.VALIDACIONES_SAT,
                        severity=AuditObservationSeverity.CRITICAL,
                        message=f"CFDI {sr.xml_uuid} tiene estado SAT fallido/cancelado.",
                        item_id=sr.xml_uuid
                    ))

            # Contabilidad (Pólizas)
            polizas_raw = []
            for p in proposals:
                polizas_raw.append({
                    "id": p.id,
                    "fecha": p.fecha.isoformat(),
                    "source_uuid": p.source_uuid,
                    "es_cuadrada": p.es_cuadrada,
                    "total_cargos": str(p.total_cargos),
                    "total_abonos": str(p.total_abonos)
                })
                if p.es_cuadrada:
                    metrics.total_polizas_cuadradas += 1
                else:
                    metrics.total_polizas_rechazadas += 1
                    observaciones.append(AuditObservation(
                        section=AuditSection.POLIZAS,
                        severity=AuditObservationSeverity.CRITICAL,
                        message=f"Póliza no cuadrada para {p.source_uuid}.",
                        item_id=p.id
                    ))

            # Conciliación
            concil_raw = []
            if conciliation:
                metrics.xmls_sin_conciliar = len(conciliation.unmatched_xmls)
                metrics.transacciones_sin_conciliar = len(conciliation.unmatched_transactions)
                metrics.matches_exactos = conciliation.exact_matches_count
                
                concil_raw.append({
                    "id": conciliation.id,
                    "matches_exactos": conciliation.exact_matches_count,
                    "unmatched_xmls": conciliation.unmatched_xmls,
                    "unmatched_transactions": conciliation.unmatched_transactions
                })
                
                if conciliation.unmatched_xmls:
                    for un_xml in conciliation.unmatched_xmls:
                        observaciones.append(AuditObservation(
                            section=AuditSection.CONCILIACION,
                            severity=AuditObservationSeverity.WARNING,
                            message=f"XML {un_xml} sin conciliar.",
                            item_id=un_xml
                        ))
                        
            # Workflow
            wf_raw = []
            for wf in workflow:
                wf_raw.append({
                    "document_id": wf.document_id,
                    "estado": wf.estado,
                    "timestamp": wf.created_at.isoformat() if wf.created_at else None
                })
            
            # Summary
            summary = AuditSummary(
                tenant_id=tenant_id,
                processing_run_id=processing_run_id
            )
            
            # Index
            index = AuditIndex(entries=[
                AuditIndexEntry(section=AuditSection.CARATULA, title="Carátula", item_count=1),
                AuditIndexEntry(section=AuditSection.RESUMEN, title="Resumen Ejecutivo", item_count=1),
                AuditIndexEntry(section=AuditSection.DOCUMENTOS, title="Documentos Adjuntos", item_count=len(attachments)),
                AuditIndexEntry(section=AuditSection.CFDI, title="CFDIs", item_count=len(xmls_raw)),
                AuditIndexEntry(section=AuditSection.VALIDACIONES_SAT, title="Resultados SAT", item_count=len(sat_raw)),
                AuditIndexEntry(section=AuditSection.POLIZAS, title="Pólizas Contables", item_count=len(polizas_raw)),
                AuditIndexEntry(section=AuditSection.CONCILIACION, title="Conciliación", item_count=len(concil_raw)),
                AuditIndexEntry(section=AuditSection.WORKFLOW, title="Historial Workflow", item_count=len(wf_raw)),
                AuditIndexEntry(section=AuditSection.OBSERVACIONES, title="Observaciones Generadas", item_count=len(observaciones))
            ])
            
            # Construir File
            return AuditFile(
                summary=summary,
                metrics=metrics,
                index=index,
                documentos=attachments,
                xmls_raw=xmls_raw,
                resultados_sat=sat_raw,
                polizas=polizas_raw,
                resultados_conciliacion=concil_raw,
                eventos_workflow=wf_raw,
                observaciones=observaciones
            )
