import unittest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from infrastructure.database.orm.base import Base
from infrastructure.database.orm.models import Document, Company
from infrastructure.database.uow import SQLAlchemyUnitOfWork
from domains.documents.identity import DocumentIdentity, Fingerprint
from domains.documents.duplicate import DuplicateDetector
from domains.documents.metadata import MetadataBuilder
from application.use_cases.search_service import SearchService
from uuid_utils import uuid7

class TestPhase9(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.uow = SQLAlchemyUnitOfWork(self.session_factory)
        
        self.company_id = str(uuid7())
        self.rfc = "TEST123456T1"
        self.doc_uuid = str(uuid7())
        self.sha256 = "dummyhash12345"
        self.fingerprint = Fingerprint.generate(self.sha256, 1024, date(2024, 1, 15), self.rfc, "CFDI")
        
        with self.uow:
            c = Company(id=self.company_id, rfc=self.rfc, razon_social="Test")
            d = Document(
                id=self.doc_uuid, 
                company_id=self.company_id, 
                hash_sha256=self.sha256, 
                fingerprint=self.fingerprint,
                tipo="CFDI", 
                tamanio_bytes=1024,
                fecha_documento=date(2024, 1, 15),
                ejercicio=2024,
                periodo=1,
                banco="BBVA",
                cuenta="1234",
                uuid_cfdi="A1B2C3D4-5678-90AB-CDEF-123456789012"
            )
            self.uow.companies.add(c)
            self.uow.documents.add(d)
            self.uow.commit()

    def test_fingerprint_deterministic(self):
        fp1 = Fingerprint.generate("hash1", 100, date(2023, 1, 1), "RFC1", "CFDI")
        fp2 = Fingerprint.generate("hash1", 100, date(2023, 1, 1), "RFC1", "CFDI")
        fp3 = Fingerprint.generate("hash2", 100, date(2023, 1, 1), "RFC1", "CFDI")
        
        self.assertEqual(fp1, fp2)
        self.assertNotEqual(fp1, fp3)

    def test_metadata_builder(self):
        identity = MetadataBuilder.build(
            document_uuid=str(uuid7()),
            sha256="hash",
            empresa_id=self.company_id,
            empresa_rfc=self.rfc,
            fecha_documento=date(2024, 5, 10),
            tipo_documento="ESTADO_CUENTA",
            origen="UPLOAD"
        )
        self.assertEqual(identity.ejercicio, 2024)
        self.assertEqual(identity.periodo, 5)

    def test_duplicate_physical(self):
        detector = DuplicateDetector(self.uow.documents)
        identity = DocumentIdentity(
            document_uuid=str(uuid7()), sha256=self.sha256, empresa_id=self.company_id, 
            empresa_rfc=self.rfc, ejercicio=2024, periodo=1, tipo_documento="PDF", 
            fecha_documento=date(2024,1,1), origen="UPLOAD"
        )
        with self.uow:
            res = detector.check_duplicate(identity, 500)
            self.assertTrue(res.is_duplicate)
            self.assertEqual(res.duplicate_type, "PHYSICAL")

    def test_duplicate_logical_uuid(self):
        detector = DuplicateDetector(self.uow.documents)
        identity = DocumentIdentity(
            document_uuid="A1B2C3D4-5678-90AB-CDEF-123456789012", # Same CFDI UUID
            sha256="different_hash", empresa_id=self.company_id, 
            empresa_rfc=self.rfc, ejercicio=2024, periodo=1, tipo_documento="CFDI", 
            fecha_documento=date(2024,1,1), origen="UPLOAD"
        )
        with self.uow:
            res = detector.check_duplicate(identity, 500)
            self.assertTrue(res.is_duplicate)
            self.assertEqual(res.duplicate_type, "LOGICAL")
            self.assertIn("Mismo UUID", res.explanation)

    def test_search_service(self):
        service = SearchService(self.uow)
        
        # Search by UUID
        res1 = service.search(uuid_cfdi="A1B2C3D4-5678-90AB-CDEF-123456789012")
        self.assertEqual(len(res1), 1)
        
        # Search by RFC
        res2 = service.search(rfc=self.rfc)
        self.assertEqual(len(res2), 1)
        
        # Search by multiple params
        res3 = service.search(banco="BBVA", ejercicio=2024, tipo_documento="CFDI")
        self.assertEqual(len(res3), 1)
        
        # Search missing
        res4 = service.search(banco="BANAMEX")
        self.assertEqual(len(res4), 0)

if __name__ == "__main__":
    unittest.main()
