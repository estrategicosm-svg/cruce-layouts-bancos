import os
import tempfile
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infrastructure.database.orm.base import Base
from infrastructure.database.uow import SQLAlchemyUnitOfWork
from use_cases.process_files import ProcessFilesAndPersistUseCase
from application.use_cases.generate_tax_file import GenerateTaxFileUseCase
from domains.reporting.models import AuditSection, AuditObservationSeverity

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
        with open(self.dummy_xml_path, 'w') as f:
            # Using a basic dummy XML. This will be processed and persisted.
            f.write('<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" TipoDeComprobante="I" SubTotal="1000.00" Total="1160.00"><cfdi:Emisor Rfc="PROVEEDOR"/><cfdi:Receptor Rfc="TENANT1"/><cfdi:Conceptos><cfdi:Concepto><cfdi:Impuestos><cfdi:Traslados><cfdi:Traslado Impuesto="002" TasaOCuota="0.160000" Importe="160.00"/></cfdi:Traslados></cfdi:Impuestos></cfdi:Concepto></cfdi:Conceptos><cfdi:Complemento><tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" UUID="DUMMY-UUID-12345"/></cfdi:Complemento></cfdi:Comprobante>')

    def tearDown(self):
        self.test_dir.cleanup()
        Base.metadata.drop_all(self.engine)

    def test_generate_tax_file_complete(self):
        # 1. Simulate processing a file
        run_id = self.process_use_case.execute([self.dummy_xml_path], "TENANT1")
        
        # 2. Generate Audit File
        audit_file = self.reporting_use_case.execute(run_id)
        
        # 3. Assertions
        self.assertEqual(audit_file.summary.processing_run_id, run_id)
        self.assertEqual(audit_file.metrics.total_documentos, 1)
        self.assertEqual(audit_file.metrics.total_xmls, 1)
        # Should have un-conciliated XML observation because there's no bank transaction
        self.assertGreater(audit_file.metrics.xmls_sin_conciliar, 0)
        
        # Check Observations
        obs_sections = [obs.section for obs in audit_file.observaciones]
        self.assertIn(AuditSection.CONCILIACION, obs_sections)
        
        # Verify JSON export
        json_output = audit_file.to_json()
        self.assertIn("DUMMY-UUID-12345", json_output)

    def test_generate_tax_file_empty(self):
        # Test what happens when run_id does not exist
        audit_file = self.reporting_use_case.execute("NON-EXISTENT-RUN-ID")
        
        self.assertEqual(audit_file.metrics.total_documentos, 0)
        self.assertEqual(audit_file.metrics.total_xmls, 0)
        
        # Should have critical observation about missing documents
        critical_obs = [obs for obs in audit_file.observaciones if obs.severity == AuditObservationSeverity.CRITICAL]
        self.assertGreater(len(critical_obs), 0)
        self.assertEqual(critical_obs[0].section, AuditSection.DOCUMENTOS)

if __name__ == '__main__':
    unittest.main()
