import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from infrastructure.database.orm.base import Base
from infrastructure.database.orm.models import Company, Document
from infrastructure.database.uow import SQLAlchemyUnitOfWork
from uuid_utils import uuid7

class TestPhase6(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        @event.listens_for(Engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
            
        # In-memory SQLite for testing persistence isolated from Postgres
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.uow = SQLAlchemyUnitOfWork(self.session_factory)
        
    def test_persistence_and_commit(self):
        company_id = str(uuid7())
        rfc = "ABC123456T1"
        
        with self.uow:
            c = Company(id=company_id, rfc=rfc, razon_social="Test Company")
            self.uow.companies.add(c)
            self.uow.commit()
            
        # Verify persistence in a new session via UoW
        with self.uow:
            persisted = self.uow.companies.get_by_rfc(rfc)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted.razon_social, "Test Company")
            
    def test_rollback(self):
        rfc = "XXX123456T1"
        try:
            with self.uow:
                c = Company(id=str(uuid7()), rfc=rfc, razon_social="Rollback Company")
                self.uow.companies.add(c)
                raise ValueError("Force rollback")
        except ValueError:
            pass
            
        with self.uow:
            persisted = self.uow.companies.get_by_rfc(rfc)
            self.assertIsNone(persisted)
            
    def test_referential_integrity(self):
        from sqlalchemy.exc import IntegrityError
        
        with self.assertRaises(IntegrityError):
            with self.uow:
                d = Document(
                    id=str(uuid7()),
                    company_id="nonexistent-id",
                    hash_sha256="abc123hash",
                    tipo="PDF",
                    tamanio_bytes=100
                )
                self.uow.documents.add(d)
                self.uow.commit()

if __name__ == "__main__":
    unittest.main()
