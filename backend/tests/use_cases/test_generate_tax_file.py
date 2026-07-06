import os
import tempfile
import unittest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infrastructure.database.orm.base import Base
from infrastructure.database.uow import SQLAlchemyUnitOfWork
from infrastructure.database.orm.models import (
    Company, Document, DocumentVersion, CanonicalXML, SATValidationResult,
    AccountingProposal, ConciliationResult, WorkflowEvent
)
from use_cases.process_files import ProcessFilesAndPersistUseCase
from application.use_cases.generate_tax_file import GenerateTaxFileUseCase
from domains.reporting.models import AuditSection, AuditObservationSeverity


def _create_valid_xml(path: str) -> str:
    content = (
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        'TipoDeComprobante="I" SubTotal="1000.00" Total="1160.00">'
        '<cfdi:Emisor Rfc="PROVEEDOR"/>'
        '<cfdi:Receptor Rfc="TENANT1"/>'
        '<cfdi:Conceptos>'
        '<cfdi:Concepto>'
        '<cfdi:Impuestos>'
        '<cfdi:Traslados>'
        '<cfdi:Traslado Impuesto="002" TasaOCuota="0.160000" Importe="160.00"/>'
        '</cfdi:Traslados>'
        '</cfdi:Impuestos>'
        '</cfdi:Concepto>'
        '</cfdi:Conceptos>'
        '<cfdi:Complemento>'
        '<tfd:TimbreFiscalDigital '
        'xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" '
        'UUID="DUMMY-UUID-12345"/>'
        '</cfdi:Complemento>'
        '</cfdi:Comprobante>'
    )
    with open(path, "w") as f:
        f.write(content)
    return path


class TestGenerateTaxFileUseCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.uow = SQLAlchemyUnitOfWork(self.session_factory)
        self.process_use_case = ProcessFilesAndPersistUseCase(self.uow)
        self.reporting_use_case = GenerateTaxFileUseCase(self.uow)
        
        self.test_dir = tempfile.TemporaryDirectory()
        self.dummy_xml_path = os.path.join(self.test_dir.name, "dummy.xml")
        _create_valid_xml(self.dummy_xml_path)

    def tearDown(self):
        self.test_dir.cleanup()
        Base.metadata.drop_all(self.engine)

    def test_generate_tax_file_complete(self):
        run_id = self.process_use_case.execute([self.dummy_xml_path], "TENANT1").run_id
        audit_file = self.reporting_use_case.execute(run_id)
        
        self.assertEqual(audit_file.summary.processing_run_id, run_id)
        self.assertEqual(audit_file.metrics.total_documentos, 1)
        self.assertEqual(audit_file.metrics.total_xmls, 1)
        # Should have un-conciliated XML observation
        self.assertGreater(audit_file.metrics.xmls_sin_conciliar, 0)
        
        obs_sections = [obs.section for obs in audit_file.observaciones]
        self.assertIn(AuditSection.CONCILIACION, obs_sections)
        
        json_output = audit_file.to_json()
        self.assertIn("DUMMY-UUID-12345", json_output)

    def test_generate_tax_file_empty(self):
        audit_file = self.reporting_use_case.execute("NON-EXISTENT-RUN-ID")
        
        self.assertEqual(audit_file.metrics.total_documentos, 0)
        self.assertEqual(audit_file.metrics.total_xmls, 0)
        
        critical_obs = [obs for obs in audit_file.observaciones if obs.severity == AuditObservationSeverity.CRITICAL]
        self.assertGreater(len(critical_obs), 0)
        self.assertEqual(critical_obs[0].section, AuditSection.DOCUMENTOS)

    def _seed_company_and_doc(self, run_id: str) -> tuple:
        with self.uow as uow:
            company_id = str(uuid.uuid4())
            doc_id = str(uuid.uuid4())

            company = Company(
                id=company_id,
                rfc="TENANT1",
                razon_social="Tenant TENANT1",
                processing_run_id=run_id
            )
            uow.companies.add(company)

            doc = Document(
                id=doc_id,
                company_id=company_id,
                hash_sha256="fakehash",
                tipo="XML",
                tamanio_bytes=100,
                processing_run_id=run_id,
                estado_workflow="RECEIVED",
                version=1
            )
            uow.documents.add(doc)

            dv = DocumentVersion(
                id=str(uuid.uuid4()),
                document_id=doc_id,
                storage_url="fake.xml",
                version_number=1,
                processing_run_id=run_id
            )
            uow.documents.add_version(dv)
            uow.commit()
        return company_id, doc_id

    def test_cancelled_cfdi_counts_as_cancelado(self):
        run_id = str(uuid.uuid4())
        _, doc_id = self._seed_company_and_doc(run_id)

        with self.uow as uow:
            xml = CanonicalXML(
                id=str(uuid.uuid4()),
                document_uuid=doc_id,
                uuid_cfdi="CANCELLED-UUID",
                rfc_emisor="EMISOR",
                rfc_receptor="TENANT1",
                tipo_cfdi="I",
                subtotal=1000,
                total=1160,
                estado_cancelacion="CANCELADO",
                processing_run_id=run_id,
                version=1
            )
            uow.xmls.add(xml)

            sat = SATValidationResult(
                id=str(uuid.uuid4()),
                xml_uuid=xml.id,
                overall_status="FAIL",
                rule_results=[
                    {"rule_name": "CFDI_STATUS", "status": "FAIL"},
                    {"rule_name": "IVA", "status": "PASS"},
                ],
                processing_run_id=run_id,
                version=1
            )
            uow.sat_results.add(sat)
            uow.commit()

        audit_file = self.reporting_use_case.execute(run_id)
        self.assertEqual(audit_file.metrics.cfdis_cancelados, 1)
        self.assertEqual(audit_file.metrics.cfdis_con_errores_validacion, 0)

    def test_failed_validation_not_cancelado(self):
        run_id = str(uuid.uuid4())
        _, doc_id = self._seed_company_and_doc(run_id)

        with self.uow as uow:
            xml = CanonicalXML(
                id=str(uuid.uuid4()),
                document_uuid=doc_id,
                uuid_cfdi="FAIL-VALIDATION-UUID",
                rfc_emisor="EMISOR",
                rfc_receptor="TENANT1",
                tipo_cfdi="I",
                subtotal=1000,
                total=1160,
                estado_cancelacion="VIGENTE",
                processing_run_id=run_id,
                version=1
            )
            uow.xmls.add(xml)

            sat = SATValidationResult(
                id=str(uuid.uuid4()),
                xml_uuid=xml.id,
                overall_status="FAIL",
                rule_results=[
                    {"rule_name": "CFDI_STATUS", "status": "PASS"},
                    {"rule_name": "IVA", "status": "FAIL"},
                ],
                processing_run_id=run_id,
                version=1
            )
            uow.sat_results.add(sat)
            uow.commit()

        audit_file = self.reporting_use_case.execute(run_id)
        self.assertEqual(audit_file.metrics.cfdis_cancelados, 0)
        self.assertEqual(audit_file.metrics.cfdis_con_errores_validacion, 1)

    def test_passing_cfdi_no_counters(self):
        run_id = str(uuid.uuid4())
        _, doc_id = self._seed_company_and_doc(run_id)

        with self.uow as uow:
            xml = CanonicalXML(
                id=str(uuid.uuid4()),
                document_uuid=doc_id,
                uuid_cfdi="PASS-UUID",
                rfc_emisor="EMISOR",
                rfc_receptor="TENANT1",
                tipo_cfdi="I",
                subtotal=1000,
                total=1160,
                estado_cancelacion="VIGENTE",
                processing_run_id=run_id,
                version=1
            )
            uow.xmls.add(xml)

            sat = SATValidationResult(
                id=str(uuid.uuid4()),
                xml_uuid=xml.id,
                overall_status="PASS",
                rule_results=[],
                processing_run_id=run_id,
                version=1
            )
            uow.sat_results.add(sat)
            uow.commit()

        audit_file = self.reporting_use_case.execute(run_id)
        self.assertEqual(audit_file.metrics.cfdis_cancelados, 0)
        self.assertEqual(audit_file.metrics.cfdis_con_errores_validacion, 0)

    def test_cancelled_vs_failed_validation_both_counted_correctly(self):
        run_id = str(uuid.uuid4())
        _, doc_id = self._seed_company_and_doc(run_id)

        with self.uow as uow:
            # Cancelled CFDI
            xml_cancelled = CanonicalXML(
                id=str(uuid.uuid4()),
                document_uuid=doc_id,
                uuid_cfdi="CANCELLED",
                rfc_emisor="EMISOR",
                rfc_receptor="TENANT1",
                tipo_cfdi="I",
                subtotal=500,
                total=580,
                estado_cancelacion="CANCELADO",
                processing_run_id=run_id,
                version=1
            )
            uow.xmls.add(xml_cancelled)
            uow.sat_results.add(SATValidationResult(
                id=str(uuid.uuid4()),
                xml_uuid=xml_cancelled.id,
                overall_status="FAIL",
                rule_results=[],
                processing_run_id=run_id,
                version=1
            ))

            # Failed validation (non-cancelled)
            xml_failed = CanonicalXML(
                id=str(uuid.uuid4()),
                document_uuid=doc_id,
                uuid_cfdi="FAILED-VAL",
                rfc_emisor="EMISOR",
                rfc_receptor="TENANT1",
                tipo_cfdi="I",
                subtotal=200,
                total=232,
                estado_cancelacion="VIGENTE",
                processing_run_id=run_id,
                version=1
            )
            uow.xmls.add(xml_failed)
            uow.sat_results.add(SATValidationResult(
                id=str(uuid.uuid4()),
                xml_uuid=xml_failed.id,
                overall_status="FAIL",
                rule_results=[],
                processing_run_id=run_id,
                version=1
            ))

            # Passing CFDI
            xml_pass = CanonicalXML(
                id=str(uuid.uuid4()),
                document_uuid=doc_id,
                uuid_cfdi="PASS",
                rfc_emisor="EMISOR",
                rfc_receptor="TENANT1",
                tipo_cfdi="I",
                subtotal=300,
                total=348,
                estado_cancelacion="VIGENTE",
                processing_run_id=run_id,
                version=1
            )
            uow.xmls.add(xml_pass)
            uow.sat_results.add(SATValidationResult(
                id=str(uuid.uuid4()),
                xml_uuid=xml_pass.id,
                overall_status="PASS",
                rule_results=[],
                processing_run_id=run_id,
                version=1
            ))

            uow.commit()

        audit_file = self.reporting_use_case.execute(run_id)
        self.assertEqual(audit_file.metrics.cfdis_cancelados, 1)
        self.assertEqual(audit_file.metrics.cfdis_con_errores_validacion, 1)
        self.assertEqual(audit_file.metrics.total_xmls, 3)

if __name__ == '__main__':
    unittest.main()
