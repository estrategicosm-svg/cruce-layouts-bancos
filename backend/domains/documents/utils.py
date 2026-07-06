import hashlib

def calculate_sha256(file_bytes: bytes) -> str:
    """
    Calculates the SHA-256 hash of a file's bytes.
    Used for ensuring document immutability and uniqueness.
    """
    hasher = hashlib.sha256()
    hasher.update(file_bytes)
    return hasher.hexdigest()

def detect_magic_bytes(file_bytes: bytes) -> str:
    """
    Detects the basic type of a file based on magic bytes (file signature).
    Currently supports PDF and XML.
    """
    if file_bytes.startswith(b'%PDF'):
        return 'PDF_STATEMENT'
    # XML can start with various byte orders or directly with <
    # A simplified check for this phase
    if b'<?xml' in file_bytes[:100].lower() or file_bytes.startswith(b'<'):
        return 'XML_CFDI'
    
    return 'UNKNOWN'
