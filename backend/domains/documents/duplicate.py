from typing import Optional, Dict
from pydantic import BaseModel
from domains.documents.identity import DocumentIdentity, Fingerprint

class DuplicateResult(BaseModel):
    is_duplicate: bool
    duplicate_type: Optional[str] = None # PHYSICAL (same hash), LOGICAL (same UUID/business identity)
    explanation: str
    existing_document_id: Optional[str] = None

class DuplicateDetector:
    """
    Evaluates physical and logical duplicates using deterministic indexing rules.
    """
    def __init__(self, document_repository):
        # We inject the document repository interface to search the DB
        self.doc_repo = document_repository

    def check_duplicate(self, identity: DocumentIdentity, tamanio_bytes: int) -> DuplicateResult:
        # 1. Physical Duplicate (Same file bytes -> Same SHA256)
        existing_by_hash = self.doc_repo.get_by_hash(identity.sha256)
        if existing_by_hash:
            return DuplicateResult(
                is_duplicate=True,
                duplicate_type="PHYSICAL",
                explanation=f"Físicamente idéntico al documento {existing_by_hash.id} (Mismo SHA256).",
                existing_document_id=existing_by_hash.id
            )

        # 2. Logical Duplicate (Same CFDI UUID or same composite fingerprint)
        # Check CFDI UUID logic
        if identity.tipo_documento == "CFDI":
            # Assuming for CFDI, document_uuid in Identity is the CFDI UUID
            # This requires a method get_by_uuid in repository (or we use search_service logic, 
            # for now we assume repo has it or we can check via fingerprint)
            existing_by_uuid = self.doc_repo.get_by_cfdi_uuid(identity.document_uuid)
            if existing_by_uuid:
                 return DuplicateResult(
                    is_duplicate=True,
                    duplicate_type="LOGICAL",
                    explanation=f"CFDI duplicado lógicamente con {existing_by_uuid.id} (Mismo UUID del SAT).",
                    existing_document_id=existing_by_uuid.id
                )
        
        # Check by Fingerprint
        fp = Fingerprint.generate(
            sha256=identity.sha256,
            tamanio_bytes=tamanio_bytes,
            fecha_documento=identity.fecha_documento,
            empresa_rfc=identity.empresa_rfc,
            tipo_documento=identity.tipo_documento
        )
        existing_by_fp = self.doc_repo.get_by_fingerprint(fp)
        if existing_by_fp:
            return DuplicateResult(
                is_duplicate=True,
                duplicate_type="LOGICAL",
                explanation=f"Duplicado lógico con {existing_by_fp.id} (Mismo Fingerprint).",
                existing_document_id=existing_by_fp.id
            )

        return DuplicateResult(
            is_duplicate=False,
            explanation="El documento es único en el sistema."
        )
