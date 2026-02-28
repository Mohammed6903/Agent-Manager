from abc import ABC, abstractmethod
from typing import Any, List, Optional

class GatewayClient(ABC):
    @abstractmethod
    async def list_agents(self) -> List[dict]:
        pass

    @abstractmethod
    async def get_config(self) -> dict:
        pass

    @abstractmethod
    async def patch_config(self, base_hash: str, raw_config: str) -> dict:
        pass

    @abstractmethod
    async def delete_agent(self, agent_id: str) -> dict:
        pass

    @abstractmethod
    async def get_status(self) -> dict:
        pass

    # ── Cron ────────────────────────────────────────────────────────────────────

    @abstractmethod
    async def cron_list(self) -> List[dict]:
        pass

    @abstractmethod
    async def cron_add(self, job: dict) -> dict:
        pass

    @abstractmethod
    async def cron_update(self, job_id: str, patch: dict) -> dict:
        pass

    @abstractmethod
    async def cron_edit(self, job_id: str, updates: dict) -> dict:
        pass

    @abstractmethod
    async def cron_remove(self, job_id: str) -> dict:
        pass

    @abstractmethod
    async def cron_run(self, job_id: str) -> dict:
        pass

    @abstractmethod
    async def cron_runs(self, job_id: str, limit: int = 20) -> List[dict]:
        pass
