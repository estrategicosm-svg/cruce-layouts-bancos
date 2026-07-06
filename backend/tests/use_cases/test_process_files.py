import os
import tempfile
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infrastructure.database.orm.base import Base
from infrastructure.database.uow import SQLAlchemyUnitOfWork
from use_cases.process_files import ProcessFilesAndPersistUseCase
from infrastructure.database.orm.models import Document, CanonicalXML, SATValidationResult, AccountingProposal, WorkflowEvent


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


def _create_corrupt_xml(path: str, seed: int = 0) -> str:
    # Mismatched closing tag — ET.parse lanza ParseError
    content = f"<root><broken>{seed}</broken></mistmatch>"
    with open(path, "w") as f:
        f.write(content)
    return path


class TestProcessFilesAndPersistUseCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.uow = SQLAlchemyUnitOfWork(self.session_factory)
        self.use_case = ProcessFilesAndPersistUseCase(self.uow)

        self.test_dir = tempfile.TemporaryDirectory()
        self.valid_xml = os.path.join(self.test_dir.name, "valid.xml")
        _create_valid_xml(self.valid_xml)

    def tearDown(self):
        self.test_dir.cleanup()
        Base.metadata.drop_all(self.engine)

    def test_process_files_persists_correctly(self):
        result = self.use_case.execute([self.valid_xml], "TENANT1")

        with self.uow as uow:
            # Check Document
            docs = uow.session.query(Document).all()
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].processing_run_id, result.run_id)
            self.assertEqual(docs[0].version, 1)

            # Check XML
            xmls = uow.session.query(CanonicalXML).all()
            self.assertEqual(len(xmls), 1)
            self.assertEqual(xmls[0].uuid_cfdi, "DUMMY-UUID-12345")
            self.assertEqual(xmls[0].processing_run_id, result.run_id)

            # Check SAT Result
            sat_res = uow.session.query(SATValidationResult).all()
            self.assertEqual(len(sat_res), 1)
            self.assertEqual(sat_res[0].processing_run_id, result.run_id)

            # Check Accounting
            acct_props = uow.session.query(AccountingProposal).all()
            self.assertEqual(len(acct_props), 1)
            self.assertEqual(acct_props[0].processing_run_id, result.run_id)
            self.assertTrue(acct_props[0].es_cuadrada)

        # Check result metadata
        self.assertEqual(result.total_files, 1)
        self.assertEqual(result.failed_files, 0)
        self.assertEqual(result.failed_file_names, [])

    def test_idempotency_same_file(self):
        # First run
        result_1 = self.use_case.execute([self.valid_xml], "TENANT1")

        # Second run with exact same file
        result_2 = self.use_case.execute([self.valid_xml], "TENANT1")

        self.assertNotEqual(result_1.run_id, result_2.run_id)

        with self.uow as uow:
            # Document should NOT be duplicated
            docs = uow.session.query(Document).all()
            self.assertEqual(len(docs), 1)

            # But XML should have version 2
            xmls = uow.session.query(CanonicalXML).all()
            self.assertEqual(len(xmls), 1)
            self.assertEqual(xmls[0].version, 2)
            self.assertEqual(xmls[0].processing_run_id, result_2.run_id)  # updated to latest run

            # Should have 2 Workflow events for RECEIVED/REPROCESSED
            events = uow.session.query(WorkflowEvent).all()
            self.assertEqual(len(events), 2)

    def test_corrupt_xml_does_not_stop_batch(self):
        corrupt_xml = os.path.join(self.test_dir.name, "corrupt.xml")
        _create_corrupt_xml(corrupt_xml)

        # Batch: valid first, corrupt second
        result = self.use_case.execute([self.valid_xml, corrupt_xml], "TENANT1")

        with self.uow as uow:
            # Both documents should exist
            docs = uow.session.query(Document).order_by(Document.created_at).all()
            self.assertEqual(len(docs), 2)

            # Valid doc should be RECEIVED (processed OK)
            valid_doc = docs[0]
            self.assertEqual(valid_doc.tipo, "XML")
            self.assertEqual(valid_doc.estado_workflow, "RECEIVED")

            # Corrupt doc should be FAILED
            corrupt_doc = docs[1]
            self.assertEqual(corrupt_doc.tipo, "XML")
            self.assertEqual(corrupt_doc.estado_workflow, "FAILED")

            # Only 1 CanonicalXML should exist (the valid one)
            xmls = uow.session.query(CanonicalXML).all()
            self.assertEqual(len(xmls), 1)
            self.assertEqual(xmls[0].uuid_cfdi, "DUMMY-UUID-12345")

            # Should have a FAILED workflow event for the corrupt document
            failed_events = (
                uow.session.query(WorkflowEvent)
                .filter(WorkflowEvent.document_id == corrupt_doc.id)
                .all()
            )
            failed_estados = [e.estado for e in failed_events]
            self.assertIn("FAILED", failed_estados)

            # The FAILED event should contain a mensaje
            failed_event = next(e for e in failed_events if e.estado == "FAILED")
            self.assertIsNotNone(failed_event.mensaje)
            self.assertIn("Parse error", failed_event.mensaje)

        # Check result metadata
        self.assertEqual(result.total_files, 2)
        self.assertEqual(result.failed_files, 1)
        self.assertEqual(len(result.failed_file_names), 1)
        self.assertTrue(result.failed_file_names[0].endswith("corrupt.xml"))

    def test_all_files_fail(self):
        corrupt_1 = os.path.join(self.test_dir.name, "corrupt1.xml")
        corrupt_2 = os.path.join(self.test_dir.name, "corrupt2.xml")
        _create_corrupt_xml(corrupt_1, seed=1)
        _create_corrupt_xml(corrupt_2, seed=2)

        result = self.use_case.execute([corrupt_1, corrupt_2], "TENANT1")

        with self.uow as uow:
            docs = uow.session.query(Document).all()
            self.assertEqual(len(docs), 2)

            for doc in docs:
                self.assertEqual(doc.estado_workflow, "FAILED")

            # No CanonicalXML should exist
            xmls = uow.session.query(CanonicalXML).all()
            self.assertEqual(len(xmls), 0)

        self.assertEqual(result.total_files, 2)
        self.assertEqual(result.failed_files, 2)
        self.assertEqual(len(result.failed_file_names), 2)


if __name__ == '__main__':
    unittest.main()
