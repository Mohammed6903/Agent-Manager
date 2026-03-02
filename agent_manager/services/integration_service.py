import json
import logging
import uuid
from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session
import httpx

from .secret_service import SecretService
from .integration_client import IntegrationClient
from .graphql_client import GraphQLClient
from .transformer import IntegrationTransformer
from ..repositories.integration_repository import IntegrationRepository
from ..models.integration import GlobalIntegration, AgentIntegration, IntegrationLog
from ..schemas.integration import GlobalIntegrationCreate, GlobalIntegrationUpdate, AgentIntegrationAssignRequest, IntegrationProxyRequest, IntegrationProxyGraphQLRequest

logger = logging.getLogger("agent_manager.services.integration_service")

class IntegrationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = IntegrationRepository(db)

    def create_global_integration(self, req: GlobalIntegrationCreate) -> GlobalIntegration:
        existing = self.repo.get_global_integration_by_name(req.name)
        if existing:
            raise HTTPException(status_code=409, detail=f"Integration with name '{req.name}' already exists.")
        
        return self.repo.create_global_integration(
            name=req.name,
            type=req.type,
            status=req.status,
            base_url=req.base_url,
            auth_scheme=req.auth_scheme,
            auth_fields=[f.model_dump() for f in req.auth_fields],
            endpoints=[e.model_dump() for e in req.endpoints],
            usage_instructions=req.usage_instructions
        )

    def update_global_integration(self, integration_id: uuid.UUID, req: GlobalIntegrationUpdate) -> GlobalIntegration:
        if req.name is not None:
             existing = self.repo.get_global_integration_by_name(req.name)
             if existing and existing.id != integration_id:
                  raise HTTPException(status_code=409, detail=f"Integration with name '{req.name}' already exists.")

        update_data = req.model_dump(exclude_unset=True)
        if "auth_fields" in update_data and update_data["auth_fields"] is not None:
            update_data["auth_fields"] = [f for f in update_data["auth_fields"]]
        if "endpoints" in update_data and update_data["endpoints"] is not None:
            update_data["endpoints"] = [e for e in update_data["endpoints"]]

        integration = self.repo.update_global_integration(integration_id, **update_data)
        if not integration:
             raise HTTPException(status_code=404, detail="Integration not found.")
        return integration

    def delete_global_integration(self, integration_id: uuid.UUID):
        if not self.repo.delete_global_integration(integration_id):
            raise HTTPException(status_code=404, detail="Integration not found.")

    def list_global_integrations(self) -> List[GlobalIntegration]:
        return self.repo.list_global_integrations()

    def get_global_integration(self, integration_id: uuid.UUID) -> GlobalIntegration:
        integration = self.repo.get_global_integration(integration_id)
        if not integration:
            raise HTTPException(status_code=404, detail="Integration not found.")
        return integration

    def assign_integration(self, integration_id: uuid.UUID, req: AgentIntegrationAssignRequest) -> AgentIntegration:
        integration = self.get_global_integration(integration_id)
        
        # Verify credentials match the required auth fields
        required_keys = {field["name"] for field in integration.auth_fields if field.get("required", False)}
        provided_keys = set(req.credentials.keys())
        
        missing_keys = required_keys - provided_keys
        if missing_keys:
             raise HTTPException(status_code=400, detail=f"Missing required credentials: {missing_keys}")

        # Store credentials in SecretService, keyed by the integration_id
        SecretService.set_secret(self.db, req.agent_id, str(integration.id), req.credentials)

        # Create mapping in DB
        return self.repo.assign_to_agent(req.agent_id, integration.id)

    def get_agent_integrations(self, agent_id: str) -> List[GlobalIntegration]:
        return self.repo.get_agent_integrations(agent_id)

    def get_agent_credentials(self, agent_id: str, integration_id: uuid.UUID) -> dict:
        assignment = self.repo.get_assignment(agent_id, integration_id)
        if not assignment:
             raise HTTPException(status_code=404, detail=f"No integration {integration_id} assigned to agent {agent_id}")
             
        creds = SecretService.get_secret(self.db, agent_id, str(integration_id))
        if not creds:
             raise HTTPException(status_code=404, detail="Credentials not found \u2014 was assignment completed successfully?")
        
        return creds

    def _inject_auth(
        self,
        auth_scheme: dict,
        creds: dict,
        headers: dict,
        params: dict,
    ) -> tuple[dict, dict]:
        """Inject credentials into headers/params based on auth_scheme. No hardcoding."""
        scheme_type = auth_scheme.get("type")

        if scheme_type == "bearer":
            token = creds.get(auth_scheme.get("token_field"))
            if token:
                headers["Authorization"] = f"Bearer {token}"

        elif scheme_type == "api_key_header":
            token = creds.get(auth_scheme.get("token_field"))
            header_name = auth_scheme.get("header_name", "X-Api-Key")
            if token:
                headers[header_name] = token

        elif scheme_type == "api_key_query":
            token = creds.get(auth_scheme.get("token_field"))
            param_name = auth_scheme.get("param_name", "api_key")
            if token:
                params = dict(params or {})
                params[param_name] = token

        elif scheme_type == "basic":
            username = creds.get(auth_scheme.get("username_field"))
            password = creds.get(auth_scheme.get("password_field"))
            if username and password:
                import base64
                encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers["Authorization"] = f"Basic {encoded}"

        # Inject any extra headers with {field} interpolation from creds
        for header_name, template in auth_scheme.get("extra_headers", {}).items():
            value = template
            for key, val in creds.items():
                value = value.replace(f"{{{key}}}", val)
            # Only inject if all placeholders were resolved
            if "{" not in value:
                headers[header_name] = value

        return headers, params

    async def async_proxy_request(self, integration_id: uuid.UUID, req: IntegrationProxyRequest) -> httpx.Response:
        """Called by the agent to make a REST request to the third-party API securely."""
        integration = self.get_global_integration(integration_id)

        if integration.api_type == "graphql":
            raise HTTPException(
                status_code=400,
                detail=f"Integration '{integration.name}' is a GraphQL integration. Use the /proxy/graphql endpoint instead.",
            )
        
        # 1. Fetch Credentials
        creds = SecretService.get_secret(self.db, req.agent_id, str(integration.id))
        if not creds:
             raise HTTPException(status_code=403, detail=f"Agent {req.agent_id} is not assigned to integration {integration.name} or missing credentials.")

        headers = dict(req.headers or {})
        params  = dict(req.params or {})

        # All auth injection is data-driven — no integration-specific code ever needed
        headers, params = self._inject_auth(integration.auth_scheme, creds, headers, params)

        # 3. Create client and dispatch
        url = f"{integration.base_url.rstrip('/')}/{req.path.lstrip('/')}"
        outgoing_body = req.body if req.body else None

        # Apply request transformers (field mapping, normalization, etc.)
        if outgoing_body and integration.request_transformers:
            outgoing_body = IntegrationTransformer.transform(
                outgoing_body,
                integration.request_transformers,
            )

        logger.info(
            "PROXY REQUEST: %s %s | body keys: %s | full body: %s",
            req.method, url,
            list(outgoing_body.keys()) if outgoing_body else "None",
            json.dumps(outgoing_body, indent=2) if outgoing_body else "None",
        )

        async with IntegrationClient(
            db=self.db,
            agent_id=req.agent_id,
            integration_id=str(integration.id),
            base_url=integration.base_url,
            endpoints=integration.endpoints
        ) as client:
            response = await client.request(
                 method=req.method,
                 url=url,
                 headers=headers,
                 params=params,
                 json=outgoing_body
            )

            # Apply response transformers if configured
            if integration.response_transformers:
                try:
                    resp_json = response.json()
                    resp_json = IntegrationTransformer.transform(
                        resp_json,
                        integration.response_transformers,
                    )
                    # Return a new response with transformed body
                    return httpx.Response(
                        status_code=response.status_code,
                        headers=response.headers,
                        content=json.dumps(resp_json),
                    )
                except (json.JSONDecodeError, ValueError):
                    pass  # response is not JSON, return as-is

            return response

    async def async_proxy_graphql(self, integration_id: uuid.UUID, req: IntegrationProxyGraphQLRequest) -> httpx.Response:
        """Called by the agent to make a GraphQL request to the third-party API securely."""
        integration = self.get_global_integration(integration_id)

        if integration.api_type != "graphql":
            raise HTTPException(
                status_code=400,
                detail=f"Integration '{integration.name}' is a REST integration. Use the /proxy endpoint instead.",
            )

        # 1. Fetch Credentials
        creds = SecretService.get_secret(self.db, req.agent_id, str(integration.id))
        if not creds:
            raise HTTPException(
                status_code=403,
                detail=f"Agent {req.agent_id} is not assigned to integration {integration.name} or missing credentials.",
            )

        headers = dict(req.headers or {})
        params: dict = {}

        # Auth injection — same data-driven approach as REST
        headers, params = self._inject_auth(integration.auth_scheme, creds, headers, params)

        async with GraphQLClient(
            db=self.db,
            agent_id=req.agent_id,
            integration_id=str(integration.id),
            base_url=integration.base_url,
            endpoints=integration.endpoints,
        ) as gql:
            return await gql.execute(
                query=req.query,
                variables=req.variables,
                operation_name=req.operation_name,
                headers=headers,
            )

    def get_graphql_client(self, agent_id: str, integration_id: uuid.UUID) -> GraphQLClient:
        """Used by other internal services needing a GraphQL wrapper."""
        integration = self.get_global_integration(integration_id)
        if integration.api_type != "graphql":
            raise HTTPException(
                status_code=400,
                detail=f"Integration '{integration.name}' is not a GraphQL integration.",
            )
        return GraphQLClient(
            db=self.db,
            agent_id=agent_id,
            integration_id=str(integration.id),
            base_url=integration.base_url,
            endpoints=integration.endpoints,
        )

    def get_integration_client(self, agent_id: str, integration_id: uuid.UUID) -> IntegrationClient:
        # Used by other internal services needing the wrapper
        integration = self.get_global_integration(integration_id)
        return IntegrationClient(
            db=self.db,
            agent_id=agent_id,
            integration_id=str(integration.id),
            base_url=integration.base_url,
            endpoints=integration.endpoints
        )

    def get_recent_logs(self, integration_id: uuid.UUID, limit: int = 20) -> List[IntegrationLog]:
        return self.repo.get_recent_logs(integration_id, limit)
