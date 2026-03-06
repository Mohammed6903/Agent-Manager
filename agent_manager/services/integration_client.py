import time
import uuid
import logging
from typing import List, Optional

import httpx
from sqlalchemy.orm import Session

from ..repositories.integration_repository import IntegrationRepository
from ..integrations.auth.base import BaseAuthHandler
from ..services.secret_service import SecretService

logger = logging.getLogger(__name__)


class IntegrationClient:
    def __init__(
        self,
        db: Session,
        agent_id: str,
        integration_name: str,
        base_url: str,
        endpoints: List[dict],
        auth_handler: Optional[BaseAuthHandler] = None,
        creds: Optional[dict] = None,
        default_headers: Optional[dict] = None,
        default_params: Optional[dict] = None
    ):
        self.db = db
        self.repo = IntegrationRepository(db)
        self.agent_id = agent_id
        self.integration_name = integration_name
        self.base_url = base_url.rstrip("/")
        self.endpoints = endpoints
        
        self.auth_handler = auth_handler
        self.creds = creds or {}
        
        self.default_headers = default_headers or {}
        self.default_params = default_params or {}
        
        self._client = httpx.AsyncClient()

    def _match_endpoint(self, method: str, url: str) -> str:
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
        # Merge defaults
        req_headers = dict(self.default_headers)
        if "headers" in kwargs and kwargs["headers"]:
            req_headers.update(kwargs["headers"])
        kwargs["headers"] = req_headers

        req_params = dict(self.default_params)
        if "params" in kwargs and kwargs["params"]:
            req_params.update(kwargs["params"])
        kwargs["params"] = req_params

        # Run Auth Handler
        if self.auth_handler:
            if self.auth_handler.requires_refresh(self.creds):
                try:
                    self.creds = await self.auth_handler.refresh(self.creds, self.db)
                    SecretService.set_secret(self.db, self.agent_id, self.integration_name, self.creds)
                except Exception as e:
                    logger.error(f"Failed to refresh credentials for {self.integration_name}: {e}")
                    raise

            kwargs["headers"], kwargs["params"] = self.auth_handler.inject(
                self.creds, kwargs["headers"], kwargs["params"], method, url
            )

        request_id = str(uuid.uuid4())
        start = time.time()
        
        status_code = 0
        error_message = None
        response = None

        try:
            response = await self._client.request(method, url, **kwargs)
            status_code = response.status_code
            if status_code >= 400:
                error_message = response.text[:500]
                
        except httpx.RequestError as e:
            error_message = str(e)
            raise
            
        finally:
            duration_ms = int((time.time() - start) * 1000)
            self.repo.create_log(
                integration_name=self.integration_name,
                agent_id=self.agent_id,
                method=method.upper(),
                endpoint=self._match_endpoint(method, url),
                status_code=status_code,
                duration_ms=duration_ms,
                request_id=request_id,
                error_message=error_message
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
