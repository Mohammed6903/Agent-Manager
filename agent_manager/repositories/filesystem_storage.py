import asyncio
import os
import shutil
from pathlib import Path
from typing import List
from .storage import StorageRepository

class FileSystemStorage(StorageRepository):
    async def ensure_dir(self, path: str) -> None:
        await asyncio.to_thread(os.makedirs, path, exist_ok=True)

    async def write_text(self, path: str, content: str) -> None:
        p = Path(path)
        await self.ensure_dir(str(p.parent))
        await asyncio.to_thread(p.write_text, content)

    async def read_text(self, path: str) -> str:
        p = Path(path)
        if not await self.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        return await asyncio.to_thread(p.read_text)

    async def exists(self, path: str) -> bool:
        return await asyncio.to_thread(Path(path).exists)

    async def list_dirs(self, path: str) -> List[str]:
        p = Path(path)
        if not await self.exists(path):
            return []
        def _list():
            return [d.name for d in p.iterdir() if d.is_dir()]
        return await asyncio.to_thread(_list)

    async def delete_dir(self, path: str) -> None:
        if await self.exists(path):
            await asyncio.to_thread(shutil.rmtree, path)

    async def is_symlink(self, path: str) -> bool:
        """Check whether *path* is a symbolic link."""
        return await asyncio.to_thread(Path(path).is_symlink)

    async def create_symlink(self, link_path: str, target_path: str) -> None:
        """Create a symbolic link at *link_path* pointing to *target_path*.

        Parent directories of *link_path* are created automatically.
        If a symlink already exists at *link_path* it is left untouched.
        """
        lp = Path(link_path)
        await self.ensure_dir(str(lp.parent))

        def _link():
            if lp.is_symlink():
                return  # never overwrite an existing symlink
            # Remove a stale regular file so the symlink can be created
            if lp.exists():
                lp.unlink()
            lp.symlink_to(target_path)

        await asyncio.to_thread(_link)
