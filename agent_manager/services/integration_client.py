import time
from typing import List

import httpx
from sqlalchemy.orm import Session

from ..models.integration import IntegrationLog

class IntegrationRepository:
    """Helper to bypass Circular Imports for Integration Client"""
    
    @staticmethod
    def create_log(db: Session, integration_id: str, agent_id: str, method: str, endpoint: str, status_code: int, duration_ms: int):
        log = IntegrationLog(
            integration_id=integration_id,
            agent_id=agent_id,
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            duration_ms=duration_ms
        )
        db.add(log)
        db.commit()


class IntegrationClient:
    def __init__(self, db: Session, agent_id: str, integration_id: str, base_url: str, endpoints: List[dict]):
        self.db = db
        self.agent_id = agent_id
        self.integration_id = integration_id
        self.base_url = base_url.rstrip("/")
        self.endpoints = endpoints  # the JSON list from GlobalIntegration
        self._client = httpx.AsyncClient()

    def _match_endpoint(self, method: str, url: str) -> str:
        # url includes base_url on most calls. 
        if url.startswith(self.base_url):
             path = url.replace(self.base_url, "")
        else:
             path = url

        matched = next(
            (e for e in self.endpoints
             if e.get("method", "").upper() == method.upper() and e.get("path") == path),
            None
        )
        return matched["path"] if matched else path

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        start = time.time()
        response = await self._client.request(method, url, **kwargs)
        duration_ms = int((time.time() - start) * 1000)
        
        IntegrationRepository.create_log(
            db=self.db,
            integration_id=self.integration_id,
            agent_id=self.agent_id,
            method=method.upper(),
            endpoint=self._match_endpoint(method, url),
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    async def get(self, url: str, **kwargs) -> httpx.Response:
         return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
         return await self.request("POST", url, **kwargs)

    async def patch(self, url: str, **kwargs) -> httpx.Response:
         return await self.request("PATCH", url, **kwargs)
         
    async def delete(self, url: str, **kwargs) -> httpx.Response:
         return await self.request("DELETE", url, **kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self._client.aclose()
