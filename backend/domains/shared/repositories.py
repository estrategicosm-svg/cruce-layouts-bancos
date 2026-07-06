from abc import ABC, abstractmethod
from typing import Optional, List, Any

class CompanyRepository(ABC):
    @abstractmethod
    def add(self, company: Any) -> None: pass
    
    @abstractmethod
    def get_by_rfc(self, rfc: str) -> Optional[Any]: pass

class DocumentRepository(ABC):
    @abstractmethod
    def add(self, document: Any) -> None: pass
    
    @abstractmethod
    def get_by_id(self, document_id: str) -> Optional[Any]: pass
    
    @abstractmethod
    def get_by_hash(self, hash_sha256: str) -> Optional[Any]: pass
    
    @abstractmethod
    def get_by_cfdi_uuid(self, uuid_cfdi: str) -> Optional[Any]: pass
    
    @abstractmethod
    def get_by_fingerprint(self, fingerprint: str) -> Optional[Any]: pass

class TransactionRepository(ABC):
    @abstractmethod
    def add(self, transaction: Any) -> None: pass
    
    @abstractmethod
    def get_by_statement_uuid(self, statement_uuid: str) -> List[Any]: pass

class XMLRepository(ABC):
    @abstractmethod
    def add(self, xml: Any) -> None: pass
    
    @abstractmethod
    def get_by_uuid(self, uuid_cfdi: str) -> Optional[Any]: pass

class EvidenceRepository(ABC):
    @abstractmethod
    def add(self, package: Any) -> None: pass
    
    @abstractmethod
    def get_by_package_uuid(self, package_uuid: str) -> Optional[Any]: pass
    
    @abstractmethod
    def get_by_document_uuid(self, document_uuid: str) -> List[Any]: pass

class WorkflowRepository(ABC):
    @abstractmethod
    def add(self, event: Any) -> None: pass
    
    @abstractmethod
    def get_by_document_id(self, document_id: str) -> List[Any]: pass
