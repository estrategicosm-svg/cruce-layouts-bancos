from abc import ABC, abstractmethod

class StorageProvider(ABC):
    """
    Abstract base class for storage operations.
    Enforces that the system never relies on local disk paths directly.
    """
    
    @abstractmethod
    def save(self, file_bytes: bytes, path: str) -> str:
        """Saves file bytes to the specified path and returns the resolved path/URL."""
        pass

    @abstractmethod
    def read(self, path: str) -> bytes:
        """Reads file bytes from the specified path."""
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Checks if a file exists at the specified path."""
        pass
