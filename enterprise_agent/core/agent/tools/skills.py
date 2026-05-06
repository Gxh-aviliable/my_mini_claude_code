"""Skill loader tool for loading specialized knowledge.

Skills are stored as SKILL.md files in a skills directory.
Each skill has YAML frontmatter with metadata (name, description)
and markdown body with the skill content.
"""

import re
from pathlib import Path
from typing import Dict, Optional

from langchain_core.tools import tool


class SkillLoader:
    """Loads and manages skills from SKILL.md files.

    Skills directory structure:
    skills/
      skill_name/
        SKILL.md  # Contains frontmatter + body
    """

    def __init__(self, skills_dir: Path = None):
        self.skills_dir = skills_dir or (Path.cwd() / "skills")
        self.skills: Dict[str, Dict] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all skills from directory."""
        if not self.skills_dir.exists():
            return

        for skill_file in sorted(self.skills_dir.rglob("SKILL.md")):
            self._load_skill_file(skill_file)

    def _load_skill_file(self, skill_file: Path) -> None:
        """Parse a single SKILL.md file."""
        try:
            text = skill_file.read_text(encoding="utf-8")

            # Parse frontmatter
            meta = {}
            body = text

            match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
            if match:
                for line in match.group(1).strip().splitlines():
                    if ":" in line:
                        key, value = line.split(":", 1)
                        meta[key.strip()] = value.strip()
                body = match.group(2).strip()

            # Use meta name or directory name
            name = meta.get("name", skill_file.parent.name)
            self.skills[name] = {
                "meta": meta,
                "body": body,
                "path": str(skill_file)
            }
        except Exception as e:
            import logging
            logging.warning("Failed to load skill %s: %s", skill_file, e)

    def descriptions(self) -> str:
        """Get formatted list of skill descriptions."""
        if not self.skills:
            return "(no skills available)"

        lines = []
        for name, skill in self.skills.items():
            desc = skill["meta"].get("description", "-")
            lines.append(f"  - {name}: {desc}")
        return "\n".join(lines)

    def load(self, name: str) -> str:
        """Load a skill by name.

        Args:
            name: Skill name to load

        Returns:
            Skill content wrapped in XML-style tags
        """
        skill = self.skills.get(name)
        if not skill:
            available = ", ".join(self.skills.keys()) if self.skills else "none"
            return f"Error: Unknown skill '{name}'. Available skills: {available}"

        return f'<skill name="{name}">\n{skill["body"]}\n</skill>'

    def list_all(self) -> str:
        """List all available skills."""
        if not self.skills:
            return "No skills available."

        lines = ["Available skills:"]
        for name, skill in self.skills.items():
            desc = skill["meta"].get("description", "")
            lines.append(f"  - {name}: {desc}")
        return "\n".join(lines)

    def reload(self) -> str:
        """Reload skills from directory."""
        self.skills.clear()
        self._load_all()
        return f"Reloaded {len(self.skills)} skills"


# Global instance
_skill_loader: Optional[SkillLoader] = None


def get_skill_loader() -> SkillLoader:
    """Get or create SkillLoader instance."""
    global _skill_loader
    if _skill_loader is None:
        _skill_loader = SkillLoader()
    return _skill_loader


@tool
def load_skill(name: str) -> str:
    """Load specialized knowledge by name.

    Skills are stored as SKILL.md files in the skills directory.
    Each skill contains expert knowledge for specific tasks.

    Args:
        name: Skill name to load

    Returns:
        Skill content for use in conversation
    """
    return get_skill_loader().load(name)


@tool
def list_skills() -> str:
    """List all available skills.

    Returns:
        Formatted list of skill names and descriptions
    """
    return get_skill_loader().list_all()


@tool
def reload_skills() -> str:
    """Reload skills from directory.

    Returns:
        Count of skills loaded
    """
    return get_skill_loader().reload()