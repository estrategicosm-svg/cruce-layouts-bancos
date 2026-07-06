import os
from pathlib import Path
from infrastructure.storage.provider import StorageProvider

class LocalStorageProvider(StorageProvider):
    """
    Local implementation of StorageProvider.
    Used for local development without Docker/MinIO.
    """
    def __init__(self, base_dir: str = "storage_data"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, file_bytes: bytes, path: str) -> str:
        full_path = self.base_dir / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(file_bytes)
        return str(full_path)

    def read(self, path: str) -> bytes:
        full_path = self.base_dir / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        with open(full_path, "rb") as f:
            return f.read()

    def exists(self, path: str) -> bool:
        return (self.base_dir / path).exists()
