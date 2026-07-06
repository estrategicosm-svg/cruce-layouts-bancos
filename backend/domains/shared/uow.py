from abc import ABC, abstractmethod
from typing import Type
from domains.shared.repositories import (
    CompanyRepository, DocumentRepository, TransactionRepository,
    XMLRepository, WorkflowRepository
)

class UnitOfWork(ABC):
    companies: CompanyRepository
    documents: DocumentRepository
    transactions: TransactionRepository
    xmls: XMLRepository
    workflow_events: WorkflowRepository

    @abstractmethod
    def __enter__(self) -> 'UnitOfWork': pass

    @abstractmethod
    def __exit__(self, exc_type: Type[BaseException], exc_val: BaseException, exc_tb: Any) -> None: pass

    @abstractmethod
    def commit(self) -> None: pass

    @abstractmethod
    def rollback(self) -> None: pass
