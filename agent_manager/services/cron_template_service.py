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
        if not template.is_public and template.created_by_user_id != user_id:
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
            print(f"Debug var {key}: type={type(var)}, content={var}")
            if key not in provided_keys:
                if var.get("default") is not None:
                    final_values[key] = var.get("default")
                elif var.get("required"):
                    missing_vars.append(key)
                
        if missing_vars:
            raise HTTPException(status_code=400, detail=f"Missing required variables: {', '.join(missing_vars)}")

        # 2. Construct doc blocks and Validate Agent Assignments
        import os
        from ..repositories.integration_repository import IntegrationRepository
        int_repo = IntegrationRepository(self.db)
        
        assigned_integrations = int_repo.get_agent_integrations(req.agent_id)
        assigned_int_ids = {intg.id for intg in assigned_integrations}

        docs = []
        
        # 1. Integration Docs & Proxy instructions (UTMOST PRIORITY)
        if template.integrations:
            docs.append("## 1. ASSIGNED INTEGRATIONS (UTMOST PRIORITY)\n"
                        "You MUST prioritize the following integrations for network requests. "
                        "Do not manually manage raw secrets or keys for these services unless absolutely necessary.")
            for t_int in template.integrations:
                if t_int.integration_id not in assigned_int_ids:
                    int_record_missing = int_repo.get_global_integration(t_int.integration_id)
                    int_name = int_record_missing.name if int_record_missing else str(t_int.integration_id)
                    raise HTTPException(
                        status_code=400,
                        detail=f"This {req.agent_id} does not have {int_name} integration assigned to it, assign it first."
                    )
                
                int_record = next((i for i in assigned_integrations if i.id == t_int.integration_id), None)
                if not int_record:
                    continue
                
                endpoints_arr = int_record.endpoints if isinstance(int_record.endpoints, list) else []
                endpoints_str = "\n".join([f"- {ep.get('method')} {ep.get('path')}: {ep.get('description')}" for ep in endpoints_arr])
                
                auth_str = str(int_record.auth_scheme) if int_record.auth_scheme else "None"
                usage_str = int_record.usage_instructions if int_record.usage_instructions else "No usage instructions."
                
                doc = f"### {int_record.name}\nBase URL: {int_record.base_url}\nAuth: {auth_str}\nUsage: {usage_str}\nAvailable endpoints:\n{endpoints_str}\n"
                docs.append(doc)

            docs.append("### HOW TO USE INTEGRATIONS (PROXY ENDPOINT)\n"
                        "To interact with these integrations, DO NOT handle credentials directly. Use the OpenClaw proxy endpoint:\n"
                        "**POST /api/integrations/{integration_id}/proxy**\n"
                        "**Body:** `{\"agent_id\": \"your-agent-id\", \"method\": \"HTTP_METHOD\", \"path\": \"/endpoint/path\", \"body\": {}}`\n"
                        "The backend will automatically inject the authenticated headers.")

        pwd = os.path.dirname(os.path.abspath(__file__))

        # 2. Other secrets (Secondary priority)
        docs.append("## 2. OTHER SECRETS & EMAILS (SECONDARY)\n"
                    "If you need to interact with a service that is NOT listed in your Assigned Integrations above, "
                    "you may need to manually fetch credentials or send emails using strictly authorized manual channels. "
                    "This is secondary and fallback behavior.")

        # 3. Garage Tool
        gt_path = os.path.join(pwd, "..", "templates", "skills", "garage-tool.md")
        if os.path.exists(gt_path):
            with open(gt_path, 'r') as f:
                gt_content = f.read().split('---', 2)[-1].strip()
                docs.append(f"## 3. Garage Feed Tool\n{gt_content}")
        
        # 4. Workspace bridge
        wb_path = os.path.join(pwd, "..", "templates", "skills", "workspace-bridge.md")
        if os.path.exists(wb_path):
            with open(wb_path, 'r') as f:
                wb_content = f.read().split('---', 2)[-1].strip()
                docs.append(f"## 4. Workspace Bridge\n{wb_content}")
                
        # 5. Context manager
        cm_path = os.path.join(pwd, "..", "templates", "skills", "context-manager.md")
        if os.path.exists(cm_path):
            with open(cm_path, 'r') as f:
                cm_content = f.read().split('---', 2)[-1].strip()
                docs.append(f"## 5. Context Manager\n{cm_content}")
        
        docs.append(f"\n**IMPORTANT: You are executing this job as agent ID: {req.agent_id}. Always use this agent_id when fetching context or calling proxy endpoints.**\n")

        prefix_docs = "\n\n".join(docs)

        # 6. Substitute in payload
        payload_message = prefix_docs + "\n\n" + self._replace_variables(template.payload_message, final_values)
        
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
