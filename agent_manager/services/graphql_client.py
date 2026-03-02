"""Scalable GraphQL client for integration proxying.

Mirrors the IntegrationClient pattern (logging, auth injection) but speaks
GraphQL instead of REST.  Every integration with api_type='graphql' is
serviced through this single client — add new GraphQL integrations without
touching this code.
"""

import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from ..models.integration import IntegrationLog

logger = logging.getLogger("agent_manager.services.graphql_client")


class _LogWriter:
    """Tiny helper to avoid a circular import with IntegrationRepository."""

    @staticmethod
    def create_log(
        db: Session,
        integration_id: str,
        agent_id: str,
        method: str,
        endpoint: str,
        status_code: int,
        duration_ms: int,
    ):
        log = IntegrationLog(
            integration_id=integration_id,
            agent_id=agent_id,
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            duration_ms=duration_ms,
        )
        db.add(log)
        db.commit()


class GraphQLClient:
    """Reusable async GraphQL client tied to a single integration.

    Usage::

        async with GraphQLClient(db, agent_id, integration_id, "https://api.example.com/graphql", endpoints) as gql:
            result = await gql.execute(
                query='query GetUser($id: ID!) { user(id: $id) { name } }',
                variables={"id": "42"},
                operation_name="GetUser",
            )
    """

    def __init__(
        self,
        db: Session,
        agent_id: str,
        integration_id: str,
        base_url: str,
        endpoints: List[dict],
    ):
        self.db = db
        self.agent_id = agent_id
        self.integration_id = integration_id
        self.base_url = base_url.rstrip("/")
        self.endpoints = endpoints  # stored operations for documentation / matching
        self._client = httpx.AsyncClient()

    # ── public API ─────────────────────────────────────────────────────────

    async def execute(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        operation_name: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Send a GraphQL request and return the raw httpx Response.

        The caller (IntegrationService) is responsible for injecting auth
        headers *before* calling this method — keeping auth logic centralised.
        """
        payload: Dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        if operation_name is not None:
            payload["operationName"] = operation_name

        merged_headers = {"Content-Type": "application/json"}
        if headers:
            merged_headers.update(headers)

        log_endpoint = self._match_operation(operation_name, query)

        start = time.time()
        response = await self._client.post(
            self.base_url,
            json=payload,
            headers=merged_headers,
        )
        duration_ms = int((time.time() - start) * 1000)

        _LogWriter.create_log(
            db=self.db,
            integration_id=self.integration_id,
            agent_id=self.agent_id,
            method="POST",
            endpoint=log_endpoint,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response

    async def query(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        operation_name: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Convenience alias — semantically a GraphQL query."""
        return await self.execute(query, variables, operation_name, headers)

    async def mutate(
        self,
        mutation: str,
        variables: Optional[Dict[str, Any]] = None,
        operation_name: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Convenience alias — semantically a GraphQL mutation."""
        return await self.execute(mutation, variables, operation_name, headers)

    # ── internals ──────────────────────────────────────────────────────────

    def _match_operation(self, operation_name: Optional[str], query: str) -> str:
        """Best-effort match against the registered endpoints / operations.

        Endpoints for GraphQL integrations are stored as:
            [{"name": "GetUser", "type": "query", "description": "..."}, ...]

        Falls back to the raw operation name or a truncated query string.
        """
        if operation_name:
            matched = next(
                (e for e in self.endpoints if e.get("name") == operation_name),
                None,
            )
            if matched:
                return f"graphql:{matched['name']}"
            return f"graphql:{operation_name}"

        # Try to extract the operation name from the query string itself
        # e.g. "query GetUser(...)" → "GetUser"
        import re
        m = re.match(r"^\s*(query|mutation|subscription)\s+(\w+)", query)
        if m:
            return f"graphql:{m.group(2)}"

        return f"graphql:anonymous"

    # ── context manager ────────────────────────────────────────────────────

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self._client.aclose()
