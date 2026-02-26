from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

class StorageRepository(ABC):
    @abstractmethod
    async def ensure_dir(self, path: str) -> None:
        pass

    @abstractmethod
    async def write_text(self, path: str, content: str) -> None:
        pass

    @abstractmethod
    async def read_text(self, path: str) -> str:
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        pass

    @abstractmethod
    async def list_dirs(self, path: str) -> List[str]:
        pass

    @abstractmethod
    async def delete_dir(self, path: str) -> None:
        pass
