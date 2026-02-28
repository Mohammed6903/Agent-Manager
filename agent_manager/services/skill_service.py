"""Skill Management Service.

Global skills live at:  {OPENCLAW_STATE_DIR}/skills/{skill-name}/SKILL.md
Agent skills live at:   {OPENCLAW_STATE_DIR}/workspace-{agent_id}/skills/{skill-name}/SKILL.md

This mirrors how IDENTITY.md and SOUL.md are handled for agents:
  - Templates are stored in agent_manager/templates/skills/
  - When a skill is created, its folder and SKILL.md are written to the state dir
  - Skills can be listed, read, updated, or deleted via the service
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

from fastapi import HTTPException

from ..config import settings
from ..schemas.chat import CreateSkillRequest, UpdateSkillRequest, SkillResponse, SkillListResponse
from ..repositories.storage import StorageRepository

logger = logging.getLogger("agent_manager.services.skill_service")

# Directory that holds the bundled default skill templates
_SKILL_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "skills"


def _to_slug(name: str) -> str:
    """Normalise a skill name to a kebab-case directory slug."""
    return name.strip().lower().replace(" ", "-")


class SkillService:
    """Manages skills on the filesystem.

    Global skills are shared across all agents.
    Agent-specific skills are scoped to a single agent's workspace.

    Directory layout::

        {OPENCLAW_STATE_DIR}/
        ├── skills/                              # global skills
        │   ├── workspace-bridge/
        │   │   └── SKILL.md
        │   └── my-custom-skill/
        │       └── SKILL.md
        └── workspace-{agent_id}/               # per-agent skills
            └── skills/
                └── my-agent-skill/
                    └── SKILL.md
    """

    def __init__(self, storage: StorageRepository):
        self.storage = storage

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _skills_root(self) -> str:
        return str(Path(settings.OPENCLAW_STATE_DIR) / "skills")

    def _skill_dir(self, slug: str) -> str:
        return str(Path(self._skills_root()) / slug)

    def _skill_md_path(self, slug: str) -> str:
        return str(Path(self._skill_dir(slug)) / "SKILL.md")

    def _load_default_template(self, slug: str) -> str:
        """Look for a bundled template matching the skill slug.

        Falls back to a minimal placeholder if no template file is found.
        """
        template_path = _SKILL_TEMPLATES_DIR / f"{slug}.md"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        # Generic placeholder for unknown skills
        return (
            f"---\nname: {slug}\ndescription: {slug} skill\n---\n\n"
            f"# {slug.replace('-', ' ').title()}\n\n"
            "Add skill instructions here.\n"
        )

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def create_skill(self, req: CreateSkillRequest) -> SkillResponse:
        """Create a new skill folder and write its SKILL.md."""
        slug = _to_slug(req.name)
        skill_md = self._skill_md_path(slug)

        if await self.storage.exists(skill_md):
            raise HTTPException(
                status_code=409,
                detail=f"Skill '{slug}' already exists. Use PATCH to update it.",
            )

        content = req.content if req.content is not None else self._load_default_template(slug)
        await self.storage.write_text(skill_md, content)

        logger.info("Skill '%s' created at %s", slug, skill_md)
        return SkillResponse(name=slug, path=skill_md, status="created")

    async def list_skills(self) -> SkillListResponse:
        """Return a list of all installed skill slugs."""
        slugs = await self.storage.list_dirs(self._skills_root())
        return SkillListResponse(skills=sorted(slugs))

    async def list_skills_with_status(self, agent_id: str) -> list[dict]:
        """Return all global skills with an `installed` flag for the given agent."""
        global_slugs = await self.storage.list_dirs(self._skills_root())
        agent_slugs = set()
        try:
            agent_slugs = set(await self.storage.list_dirs(self._agent_skills_root(agent_id)))
        except Exception:
            pass  # agent may not have a skills dir yet

        return [
            {"name": slug, "installed": slug in agent_slugs}
            for slug in sorted(global_slugs)
        ]

    async def get_skill(self, skill_name: str) -> SkillResponse:
        """Read the SKILL.md content for a given skill, returned as a SkillResponse."""
        slug = _to_slug(skill_name)
        skill_md = self._skill_md_path(slug)

        if not await self.storage.exists(skill_md):
            raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found.")

        return SkillResponse(name=slug, path=skill_md, status="ok")

    async def get_skill_content(self, skill_name: str) -> str:
        """Return the raw SKILL.md text for a given skill."""
        slug = _to_slug(skill_name)
        skill_md = self._skill_md_path(slug)

        if not await self.storage.exists(skill_md):
            raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found.")

        return await self.storage.read_text(skill_md)

    async def update_skill(self, skill_name: str, req: UpdateSkillRequest) -> SkillResponse:
        """Overwrite the SKILL.md content for an existing skill."""
        slug = _to_slug(skill_name)
        skill_md = self._skill_md_path(slug)

        if not await self.storage.exists(skill_md):
            raise HTTPException(
                status_code=404,
                detail=f"Skill '{slug}' not found. Use POST to create it first.",
            )

        await self.storage.write_text(skill_md, req.content)

        logger.info("Skill '%s' updated", slug)
        return SkillResponse(name=slug, path=skill_md, status="updated")

    async def sync_skill(self, skill_name: str) -> SkillResponse:
        """Overwrite the SKILL.md content for an existing skill with its default template."""
        slug = _to_slug(skill_name)
        skill_md = self._skill_md_path(slug)

        if not await self.storage.exists(skill_md):
            raise HTTPException(
                status_code=404,
                detail=f"Skill '{slug}' not found. Use POST to create it first.",
            )

        content = self._load_default_template(slug)
        await self.storage.write_text(skill_md, content)

        logger.info("Skill '%s' synced with default template", slug)
        return SkillResponse(name=slug, path=skill_md, status="synced")

    async def delete_skill(self, skill_name: str) -> dict:
        """Remove a skill's directory and all its contents."""
        slug = _to_slug(skill_name)
        skill_dir = self._skill_dir(slug)

        if not await self.storage.exists(skill_dir):
            raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found.")

        await self.storage.delete_dir(skill_dir)

        logger.info("Skill '%s' deleted", slug)
        return {"status": "deleted", "name": slug}

    # ── Agent-scoped helpers ──────────────────────────────────────────────────

    def _agent_skills_root(self, agent_id: str) -> str:
        return str(Path(settings.OPENCLAW_STATE_DIR) / f"workspace-{agent_id}" / "skills")

    def _agent_skill_dir(self, agent_id: str, slug: str) -> str:
        return str(Path(self._agent_skills_root(agent_id)) / slug)

    def _agent_skill_md_path(self, agent_id: str, slug: str) -> str:
        return str(Path(self._agent_skill_dir(agent_id, slug)) / "SKILL.md")

    # ── Agent-scoped CRUD ─────────────────────────────────────────────────────

    async def create_agent_skill(self, agent_id: str, req: CreateSkillRequest) -> SkillResponse:
        """Create a skill inside a specific agent's workspace."""
        slug = _to_slug(req.name)
        skill_md = self._agent_skill_md_path(agent_id, slug)

        if await self.storage.exists(skill_md):
            raise HTTPException(
                status_code=409,
                detail=f"Skill '{slug}' already exists for agent '{agent_id}'. Use PATCH to update it.",
            )

        content = req.content if req.content is not None else self._load_default_template(slug)
        await self.storage.write_text(skill_md, content)

        logger.info("Skill '%s' created for agent '%s' at %s", slug, agent_id, skill_md)
        return SkillResponse(name=slug, path=skill_md, status="created")

    async def list_agent_skills(self, agent_id: str) -> SkillListResponse:
        """Return all skill slugs installed for a specific agent."""
        slugs = await self.storage.list_dirs(self._agent_skills_root(agent_id))
        return SkillListResponse(skills=sorted(slugs))

    async def get_agent_skill(self, agent_id: str, skill_name: str) -> SkillResponse:
        """Get metadata for an agent-specific skill."""
        slug = _to_slug(skill_name)
        skill_md = self._agent_skill_md_path(agent_id, slug)

        if not await self.storage.exists(skill_md):
            raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found for agent '{agent_id}'.")

        return SkillResponse(name=slug, path=skill_md, status="ok")

    async def get_agent_skill_content(self, agent_id: str, skill_name: str) -> str:
        """Return the raw SKILL.md text for an agent-specific skill."""
        slug = _to_slug(skill_name)
        skill_md = self._agent_skill_md_path(agent_id, slug)

        if not await self.storage.exists(skill_md):
            raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found for agent '{agent_id}'.")

        return await self.storage.read_text(skill_md)

    async def update_agent_skill(self, agent_id: str, skill_name: str, req: UpdateSkillRequest) -> SkillResponse:
        """Overwrite the SKILL.md content for an agent-specific skill."""
        slug = _to_slug(skill_name)
        skill_md = self._agent_skill_md_path(agent_id, slug)

        if not await self.storage.exists(skill_md):
            raise HTTPException(
                status_code=404,
                detail=f"Skill '{slug}' not found for agent '{agent_id}'. Use POST to create it first.",
            )

        await self.storage.write_text(skill_md, req.content)

        logger.info("Skill '%s' updated for agent '%s'", slug, agent_id)
        return SkillResponse(name=slug, path=skill_md, status="updated")

    async def sync_agent_skill(self, agent_id: str, skill_name: str) -> SkillResponse:
        """Overwrite the SKILL.md content for an agent-specific skill with its default template."""
        slug = _to_slug(skill_name)
        skill_md = self._agent_skill_md_path(agent_id, slug)

        if not await self.storage.exists(skill_md):
            raise HTTPException(
                status_code=404,
                detail=f"Skill '{slug}' not found for agent '{agent_id}'. Use POST to create it first.",
            )

        content = self._load_default_template(slug)
        await self.storage.write_text(skill_md, content)

        logger.info("Skill '%s' synced with default template for agent '%s'", slug, agent_id)
        return SkillResponse(name=slug, path=skill_md, status="synced")

    async def delete_agent_skill(self, agent_id: str, skill_name: str) -> dict:
        """Remove an agent-specific skill directory."""
        slug = _to_slug(skill_name)
        skill_dir = self._agent_skill_dir(agent_id, slug)

        if not await self.storage.exists(skill_dir):
            raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found for agent '{agent_id}'.")

        await self.storage.delete_dir(skill_dir)

        logger.info("Skill '%s' deleted for agent '%s'", slug, agent_id)
        return {"status": "deleted", "name": slug, "agent_id": agent_id}

    async def install_global_skill(self, agent_id: str, skill_name: str) -> SkillResponse:
        """Copy a globally-installed skill into an agent's workspace."""
        slug = _to_slug(skill_name)

        # Check global skill exists
        global_md = self._skill_md_path(slug)
        if not await self.storage.exists(global_md):
            raise HTTPException(status_code=404, detail=f"Global skill '{slug}' not found.")

        # Check not already installed on agent
        agent_md = self._agent_skill_md_path(agent_id, slug)
        if await self.storage.exists(agent_md):
            raise HTTPException(
                status_code=409,
                detail=f"Skill '{slug}' is already installed for agent '{agent_id}'.",
            )

        # Copy content
        content = await self.storage.read_text(global_md)
        await self.storage.write_text(agent_md, content)

        logger.info("Global skill '%s' installed for agent '%s'", slug, agent_id)
        return SkillResponse(name=slug, path=agent_md, status="installed")
