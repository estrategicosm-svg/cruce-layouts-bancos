from typing import Optional, List, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from infrastructure.database.orm.models import (
    Company, Document, DocumentVersion, CanonicalStatement,
    CanonicalTransaction, CanonicalXML, SATValidationResult,
    AccountingProposal, ConciliationResult, MatchCandidate,
    EvidencePackage, WorkflowEvent
)

class SQLAlchemyCompanyRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, company: Company) -> None:
        self.session.add(company)

    def get_by_rfc(self, rfc: str) -> Optional[Company]:
        return self.session.query(Company).filter_by(rfc=rfc).first()

class SQLAlchemyDocumentRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, document: Document) -> None:
        self.session.add(document)

    def add_version(self, version: DocumentVersion) -> None:
        self.session.add(version)

    def get_by_id(self, document_id: str) -> Optional[Document]:
        return self.session.query(Document).filter_by(id=document_id).first()

    def get_by_hash(self, hash_sha256: str) -> Optional[Document]:
        return self.session.query(Document).filter(Document.hash_sha256 == hash_sha256).first()
        
    def get_by_cfdi_uuid(self, uuid_cfdi: str) -> Optional[Document]:
        return self.session.query(Document).filter(Document.uuid_cfdi == uuid_cfdi).first()
        
    def get_by_fingerprint(self, fingerprint: str) -> Optional[Document]:
        return self.session.query(Document).filter(Document.fingerprint == fingerprint).first()

    def get_latest_version(self, document_id: str) -> Optional[DocumentVersion]:
        return self.session.query(DocumentVersion).filter_by(document_id=document_id).order_by(desc(DocumentVersion.version_number)).first()

    def get_all_by_run_id(self, run_id: str) -> List[Document]:
        return self.session.query(Document).filter_by(processing_run_id=run_id).all()


class SQLAlchemyStatementRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, statement: CanonicalStatement) -> None:
        self.session.add(statement)

    def get_by_document_uuid(self, document_uuid: str) -> Optional[CanonicalStatement]:
        return self.session.query(CanonicalStatement).filter_by(document_uuid=document_uuid).first()


class SQLAlchemyTransactionRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, transaction: CanonicalTransaction) -> None:
        self.session.add(transaction)

    def get_by_statement_uuid(self, statement_uuid: str) -> List[CanonicalTransaction]:
        return self.session.query(CanonicalTransaction).filter_by(statement_uuid=statement_uuid).all()


class SQLAlchemyXMLRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, xml: CanonicalXML) -> None:
        self.session.add(xml)

    def get_by_uuid(self, uuid_cfdi: str) -> Optional[CanonicalXML]:
        return self.session.query(CanonicalXML).filter_by(uuid_cfdi=uuid_cfdi).first()

    def get_all_by_run_id(self, run_id: str) -> List[CanonicalXML]:
        return self.session.query(CanonicalXML).filter_by(processing_run_id=run_id).all()


class SQLAlchemySATResultRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, result: SATValidationResult) -> None:
        self.session.add(result)

    def get_all_by_run_id(self, run_id: str) -> List[SATValidationResult]:
        return self.session.query(SATValidationResult).filter_by(processing_run_id=run_id).all()


class SQLAlchemyAccountingRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, proposal: AccountingProposal) -> None:
        self.session.add(proposal)

    def get_all_by_run_id(self, run_id: str) -> List[AccountingProposal]:
        return self.session.query(AccountingProposal).filter_by(processing_run_id=run_id).all()


class SQLAlchemyConciliationRepository:
    def __init__(self, session: Session):
        self.session = session

    def add_result(self, result: ConciliationResult) -> None:
        self.session.add(result)

    def add_match(self, match: MatchCandidate) -> None:
        self.session.add(match)

    def get_result_by_run_id(self, run_id: str) -> Optional[ConciliationResult]:
        return self.session.query(ConciliationResult).filter_by(processing_run_id=run_id).first()

    def get_matches_by_result_id(self, result_id: str) -> List[MatchCandidate]:
        return self.session.query(MatchCandidate).filter_by(conciliation_result_id=result_id).all()


class SQLAlchemyEvidenceRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, evidence: EvidencePackage) -> None:
        self.session.add(evidence)


class SQLAlchemyWorkflowRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, event: WorkflowEvent) -> None:
        self.session.add(event)

    def get_by_document_id(self, document_id: str) -> List[WorkflowEvent]:
        return self.session.query(WorkflowEvent).filter_by(document_id=document_id).all()

    def get_all_by_run_id(self, run_id: str) -> List[WorkflowEvent]:
        return self.session.query(WorkflowEvent).filter_by(processing_run_id=run_id).all()
