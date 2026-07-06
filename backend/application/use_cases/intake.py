from typing import Tuple
from uuid_utils import uuid7
from domains.documents.utils import calculate_sha256, detect_magic_bytes
from domains.shared.canonical_models import CanonicalDocument
from infrastructure.storage.provider import StorageProvider

def process_document_intake(
    file_bytes: bytes, 
    empresa_rfc: str, 
    storage_provider: StorageProvider
) -> Tuple[CanonicalDocument, str]:
    """
    Core Use Case for intaking a document.
    - Calculates SHA-256
    - Detects type
    - Saves to storage
    - Creates CanonicalDocument
    Returns a tuple of (CanonicalDocument, storage_url).
    """
    
    # 1. Integrity check
    file_hash = calculate_sha256(file_bytes)
    
    # 2. Type detection
    doc_type = detect_magic_bytes(file_bytes)
    
    # 3. Create canonical model representation
    doc_uuid = str(uuid7())
    tamanio = len(file_bytes)
    
    document = CanonicalDocument(
        uuid=doc_uuid,
        empresa_rfc=empresa_rfc,
        hash_sha256=file_hash,
        tipo=doc_type,
        tamanio_bytes=tamanio,
        estado_workflow="RECIBIDO"
    )
    
    # 4. Storage strategy
    # The path is abstracted: {rfc}/{tipo}/{hash}
    storage_path = f"{empresa_rfc}/{doc_type}/{file_hash}"
    
    storage_url = storage_provider.save(file_bytes, storage_path)
    
    # 5. Workflow registration
    # In full implementation, this would emit an event to Workflow domain
    
    return document, storage_url
