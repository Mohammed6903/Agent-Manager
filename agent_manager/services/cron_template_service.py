from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
import json

from ..models.cron_template import CronTemplate
from ..schemas.cron_template import CronTemplateCreate, CronTemplateUpdate, CronTemplateInstantiateRequest
from ..repositories.cron_template_repository import CronTemplateRepository
from ..services.cron_service import CronService
from ..schemas.cron import CreateCronRequest
from ..clients.gateway_client import GatewayClient

class CronTemplateService:
    def __init__(self, db: Session, gateway_client: GatewayClient):
        self.db = db
        self.repo = CronTemplateRepository(db)
        self.cron_service = CronService(gateway_client, db)

    def create_template(self, user_id: str, data: CronTemplateCreate) -> CronTemplate:
        return self.repo.create(user_id, data)

    def get_template(self, template_id: str, user_id: str) -> CronTemplate:
        template = self.repo.get_by_id(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        if template.is_public is False and template.created_by_user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to view this template")
        return template

    def list_templates(self, user_id: str) -> List[CronTemplate]:
        return self.repo.list_templates(user_id)

    def update_template(self, template_id: str, user_id: str, data: CronTemplateUpdate) -> CronTemplate:
        try:
            template = self.repo.update(template_id, user_id, data)
            if not template:
                raise HTTPException(status_code=404, detail="Template not found")
            return template
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))

    def delete_template(self, template_id: str, user_id: str):
        try:
            deleted = self.repo.delete(template_id, user_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="Template not found")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))

    def _replace_variables(self, text: str, variable_values: dict) -> str:
        """Helper to replace placeholders securely"""
        if not text:
            return text
        result = text
        for key, val in variable_values.items():
            result = result.replace(f"{{{key}}}", str(val))
        return result

    def _replace_variables_recursive(self, data: any, variable_values: dict) -> any:
        """Recursively replace variables in dicts and lists (for pipeline_template)"""
        if isinstance(data, dict):
            return {k: self._replace_variables_recursive(v, variable_values) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._replace_variables_recursive(v, variable_values) for v in data]
        elif isinstance(data, str):
             # Ensure a full string match replaces to string. But we don't automatically parse strings to ints here
             # If exact match to a block is required for type safety that could be improved, but string replace is expected.
            return self._replace_variables(data, variable_values)
        return data

    async def instantiate_template(self, template_id: str, req: CronTemplateInstantiateRequest) -> dict:
        template = self.get_template(template_id, req.user_id)
        
        # 1. Validate required variables
        provided_keys = set(req.variable_values.keys())
        missing_vars = []
        final_values = dict(req.variable_values)
        
        for var in template.variables:
            # template.variables is a list of dicts because it's stored as JSON
            key = var["key"]

            if key not in provided_keys:
                if var.get("default") is not None:
                    final_values[key] = var.get("default")
                elif var.get("required"):
                    missing_vars.append(key)
                
        if missing_vars:
            raise HTTPException(status_code=400, detail=f"Missing required variables: {', '.join(missing_vars)}")

        # 2. Validate agent integration assignments
        from ..repositories.integration_repository import IntegrationRepository
        from ..config import settings as app_settings
        from ..integrations import INTEGRATION_REGISTRY
        int_repo = IntegrationRepository(self.db)

        assigned_integrations = int_repo.get_agent_integrations(req.agent_id)
        assigned_names = {intg.integration_name for intg in assigned_integrations}

        server_url = app_settings.SERVER_URL.rstrip("/")

        # ── Build a compact, action-oriented system context ──────────────────
        docs = []

        docs.append(
            f"## EXECUTION IDENTITY\n"
            f"Agent ID: `{req.agent_id}`\n"
            f"Always use this agent_id in every proxy call and context request."
        )

        # ── Integration proxy instructions (the ONLY way to call APIs) ───────
        if template.integrations:
            docs.append(
                "## INTEGRATIONS — USE PROXY ONLY\n"
                "You MUST call every external API through the integration proxy. "
                "NEVER call an external base URL directly. NEVER manage auth tokens yourself. "
                "The proxy injects authentication automatically.\n"
                "IMPORTANT: When calling the proxy with curl, always use Content-Type: application/json "
                "and pass valid JSON in the -d flag. Do NOT use shell variables inside JSON strings."
            )

            for t_int in template.integrations:
                iname = t_int.integration_name
                if iname not in assigned_names:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Agent {req.agent_id} does not have '{iname}' integration assigned. Assign it first."
                    )

                # Get the integration class from registry for documentation
                int_cls = INTEGRATION_REGISTRY.get(iname)
                if not int_cls:
                    # This shouldn't happen if it was allowed to be created in template, but safety first
                    continue

                endpoints_str = "\n".join(
                    [f"  - {ep.method} {ep.path} — {ep.description}" for ep in int_cls.endpoints]
                )

                usage_str = int_cls.usage_instructions.strip() if int_cls.usage_instructions else ""
                usage_block = f"\nUsage notes: {usage_str}" if usage_str else ""

                proxy_url = f"{server_url}/api/integrations/{iname}/proxy"

                # Build a concrete curl example for the first endpoint (or a generic one)
                example_method = "POST"
                example_path = "/example"
                if int_cls.endpoints:
                    example_method = int_cls.endpoints[0].method
                    example_path = int_cls.endpoints[0].path

                doc = (
                    f"### {int_cls.display_name}\n"
                    f"Integration Name: {iname}\n"
                    f"Proxy URL: POST {proxy_url}\n\n"
                    f"curl example (adapt method, path, and body for each call):\n"
                    f"curl -X POST {proxy_url} "
                    f"-H 'Content-Type: application/json' "
                    f"""-d '{{"agent_id": "{req.agent_id}", "method": "{example_method}", "path": "{example_path}", "body": {{}}}}'"""
                    f"\n\n"
                    f"Required JSON fields: agent_id (string), method (string), path (string), body (object)\n"
                    f"Available endpoints:\n{endpoints_str}"
                    f"{usage_block}\n"
                )
                docs.append(doc)

        prefix_docs = "\n\n".join(docs)

        # ── Substitute variables in the user's payload ───────────────────────
        payload_message = prefix_docs + "\n\n---\n\n" + self._replace_variables(template.payload_message, final_values)
        
        # 3. Substitute in pipeline
        pipeline_template = template.pipeline_template
        if pipeline_template:
            pipeline_template = self._replace_variables_recursive(pipeline_template, final_values)

        # 4. Create actual cron job
        cron_req = CreateCronRequest(
            name=f"{template.name}",
            agent_id=req.agent_id,
            schedule_kind=template.schedule_kind,
            schedule_expr=template.schedule_expr,
            schedule_tz=template.schedule_tz,
            schedule_human=template.schedule_human,
            session_target=template.session_target,
            payload_message=payload_message,
            delivery_mode=template.delivery_mode,
            enabled=True,
            pipeline_template=pipeline_template,
            user_id=req.user_id,
            session_id=req.session_id
        )
        
        job_id = await self.cron_service.create_cron(cron_req)
        return {"job_id": job_id, "message": "Cron job created from template"}
