from typing import List, Optional
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session
from ..models.cron_template import CronTemplate
from ..schemas.cron_template import CronTemplateCreate, CronTemplateUpdate


class CronTemplateRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: str, data: CronTemplateCreate) -> CronTemplate:
        template = CronTemplate(
            created_by_user_id=user_id,
            org_id=data.org_id,
            is_public=data.is_public,
            name=data.name,
            description=data.description,
            category=data.category,
            variables=[v.model_dump() for v in data.variables],
            schedule_kind=data.schedule_kind,
            schedule_expr=data.schedule_expr,
            schedule_tz=data.schedule_tz,
            schedule_human=data.schedule_human,
            session_target=data.session_target,
            delivery_mode=data.delivery_mode,
            payload_message=data.payload_message,
            pipeline_template=data.pipeline_template,
        )
        
        from ..models.cron_template import CronTemplateIntegration
        for integration_name in data.required_integrations:
            template.integrations.append(CronTemplateIntegration(integration_name=integration_name))

        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def get_by_id(self, template_id: str) -> Optional[CronTemplate]:
        return self.db.execute(
            select(CronTemplate).where(CronTemplate.id == template_id)
        ).scalar_one_or_none()

    def list_templates(self, user_id: str, org_id: str | None = None) -> List[CronTemplate]:
        stmt = select(CronTemplate).where(
            or_(
                # Always see your own templates regardless of anything
                CronTemplate.created_by_user_id == user_id,
                # See org templates only if public=True AND org matches
                and_(
                    CronTemplate.is_public == True,
                    CronTemplate.org_id == org_id,
                ) if org_id else False,
            )
        )
        return list(self.db.execute(stmt).scalars().all())

    def update(self, template_id: str, user_id: str, data: CronTemplateUpdate) -> Optional[CronTemplate]:
        template = self.get_by_id(template_id)
        if not template:
            return None
        
        # Only owner can update
        if template.created_by_user_id != user_id:
            raise PermissionError("Only the owner can update this template.")
            
        update_data = data.model_dump(exclude_unset=True)
        if "variables" in update_data and update_data["variables"] is not None:
            update_data["variables"] = [v.model_dump() for v in data.variables]

        if "required_integrations" in update_data:
            integrations_ids = update_data.pop("required_integrations")
            if integrations_ids is not None:
                template.integrations.clear()
                from ..models.cron_template import CronTemplateIntegration
                for int_name in integrations_ids:
                    template.integrations.append(CronTemplateIntegration(integration_name=int_name))

        for key, value in update_data.items():
            setattr(template, key, value)
            
        self.db.commit()
        self.db.refresh(template)
        return template

    def delete(self, template_id: str, user_id: str) -> bool:
        template = self.get_by_id(template_id)
        if not template:
            return False
            
        # Only owner can delete
        if template.created_by_user_id != user_id:
            raise PermissionError("Only the owner can delete this template.")
            
        self.db.delete(template)
        self.db.commit()
        return True
