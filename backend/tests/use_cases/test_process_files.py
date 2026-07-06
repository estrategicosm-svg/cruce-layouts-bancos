import os
import tempfile
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infrastructure.database.orm.base import Base
from infrastructure.database.uow import SQLAlchemyUnitOfWork
from use_cases.process_files import ProcessFilesAndPersistUseCase
from infrastructure.database.orm.models import Document, CanonicalXML, SATValidationResult, AccountingProposal, WorkflowEvent

class TestProcessFilesAndPersistUseCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.uow = SQLAlchemyUnitOfWork(self.session_factory)
        self.use_case = ProcessFilesAndPersistUseCase(self.uow)
        
        self.test_dir = tempfile.TemporaryDirectory()
        self.dummy_xml_path = os.path.join(self.test_dir.name, "dummy.xml")
        with open(self.dummy_xml_path, 'w') as f:
            f.write('<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" TipoDeComprobante="I" SubTotal="1000.00" Total="1160.00"><cfdi:Emisor Rfc="PROVEEDOR"/><cfdi:Receptor Rfc="TENANT1"/><cfdi:Conceptos><cfdi:Concepto><cfdi:Impuestos><cfdi:Traslados><cfdi:Traslado Impuesto="002" TasaOCuota="0.160000" Importe="160.00"/></cfdi:Traslados></cfdi:Impuestos></cfdi:Concepto></cfdi:Conceptos><cfdi:Complemento><tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" UUID="DUMMY-UUID-12345"/></cfdi:Complemento></cfdi:Comprobante>')

    def tearDown(self):
        self.test_dir.cleanup()
        Base.metadata.drop_all(self.engine)

    def test_process_files_persists_correctly(self):
        run_id = self.use_case.execute([self.dummy_xml_path], "TENANT1")
        
        with self.uow as uow:
            # Check Document
            docs = uow.session.query(Document).all()
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].processing_run_id, run_id)
            self.assertEqual(docs[0].version, 1)
            
            # Check XML
            xmls = uow.session.query(CanonicalXML).all()
            self.assertEqual(len(xmls), 1)
            self.assertEqual(xmls[0].uuid_cfdi, "DUMMY-UUID-12345")
            self.assertEqual(xmls[0].processing_run_id, run_id)
            
            # Check SAT Result
            sat_res = uow.session.query(SATValidationResult).all()
            self.assertEqual(len(sat_res), 1)
            self.assertEqual(sat_res[0].processing_run_id, run_id)
            
            # Check Accounting
            acct_props = uow.session.query(AccountingProposal).all()
            self.assertEqual(len(acct_props), 1)
            self.assertEqual(acct_props[0].processing_run_id, run_id)
            self.assertTrue(acct_props[0].es_cuadrada)

    def test_idempotency_same_file(self):
        # First run
        run_id_1 = self.use_case.execute([self.dummy_xml_path], "TENANT1")
        
        # Second run with exact same file
        run_id_2 = self.use_case.execute([self.dummy_xml_path], "TENANT1")
        
        self.assertNotEqual(run_id_1, run_id_2)
        
        with self.uow as uow:
            # Document should NOT be duplicated
            docs = uow.session.query(Document).all()
            self.assertEqual(len(docs), 1)
            
            # But XML should have version 2
            xmls = uow.session.query(CanonicalXML).all()
            self.assertEqual(len(xmls), 1)
            self.assertEqual(xmls[0].version, 2)
            self.assertEqual(xmls[0].processing_run_id, run_id_2) # updated to latest run
            
            # Should have 2 Workflow events for RECEIVED/REPROCESSED
            events = uow.session.query(WorkflowEvent).all()
            self.assertEqual(len(events), 2)

if __name__ == '__main__':
    unittest.main()
