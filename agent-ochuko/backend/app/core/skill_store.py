"""
Skill Library Store Module for Agent Ochuko.
Saves validated Python scripts and document processing routines created during successful tasks
as reusable agent skills for future sessions.
"""
import json
import os
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SkillEntry(BaseModel):
    name: str
    description: str
    code_content: str
    tags: List[str] = []


class SkillStore:
    """Indexed repository of validated agent skills."""

    def __init__(self, storage_dir: str = "/tmp/ochuko_skills"):
        self.storage_dir = os.path.abspath(storage_dir).replace("\\", "/")
        os.makedirs(self.storage_dir, exist_ok=True)
        self.skills: Dict[str, SkillEntry] = {}
        self._load_skills()

    def _load_skills(self):
        """Loads skills from storage directory."""
        if not os.path.exists(self.storage_dir):
            return

        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.storage_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        skill = SkillEntry(**data)
                        self.skills[skill.name] = skill
                except Exception as e:
                    logger.error(f"Failed to load skill file {fname}: {e}")

    def save_skill(self, name: str, description: str, code_content: str, tags: List[str] = None) -> SkillEntry:
        """Saves a new skill entry to the repository."""
        tags = tags or []
        skill = SkillEntry(name=name, description=description, code_content=code_content, tags=tags)
        self.skills[name] = skill

        fpath = os.path.join(self.storage_dir, f"{name}.json")
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(skill.model_dump(), f, indent=2)
            logger.info(f"Saved skill '{name}' to SkillStore: {fpath}")
        except Exception as e:
            logger.error(f"Failed to persist skill '{name}': {e}")

        return skill

    def find_skills(self, query: str) -> List[SkillEntry]:
        """Finds matching skills by keyword query."""
        query_lower = query.lower()
        matches = []
        for skill in self.skills.values():
            if query_lower in skill.name.lower() or query_lower in skill.description.lower():
                matches.append(skill)
        return matches


skill_store = SkillStore()
