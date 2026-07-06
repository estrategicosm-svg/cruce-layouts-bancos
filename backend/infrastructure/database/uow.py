from typing import Any, Type
from sqlalchemy.orm import sessionmaker
from infrastructure.database.repositories.sqlalchemy_repos import (
    SQLAlchemyCompanyRepository,
    SQLAlchemyDocumentRepository,
    SQLAlchemyStatementRepository,
    SQLAlchemyTransactionRepository,
    SQLAlchemyXMLRepository,
    SQLAlchemySATResultRepository,
    SQLAlchemyAccountingRepository,
    SQLAlchemyConciliationRepository,
    SQLAlchemyEvidenceRepository,
    SQLAlchemyWorkflowRepository
)

class SQLAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def __enter__(self) -> 'SQLAlchemyUnitOfWork':
        self.session = self.session_factory()
        self.companies = SQLAlchemyCompanyRepository(self.session)
        self.documents = SQLAlchemyDocumentRepository(self.session)
        self.statements = SQLAlchemyStatementRepository(self.session)
        self.transactions = SQLAlchemyTransactionRepository(self.session)
        self.xmls = SQLAlchemyXMLRepository(self.session)
        self.sat_results = SQLAlchemySATResultRepository(self.session)
        self.accounting = SQLAlchemyAccountingRepository(self.session)
        self.conciliation = SQLAlchemyConciliationRepository(self.session)
        self.evidences = SQLAlchemyEvidenceRepository(self.session)
        self.workflow_events = SQLAlchemyWorkflowRepository(self.session)
        return self

    def __exit__(self, exc_type: Type[BaseException], exc_val: BaseException, exc_tb: Any) -> None:
        if exc_type:
            self.rollback()
        self.session.close()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
