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


# Per-user instances cache
_skill_loaders: Dict[int, SkillLoader] = {}


def get_skill_loader() -> SkillLoader:
    """Get or create SkillLoader instance for current user."""
    from enterprise_agent.core.agent.tools.workspace import get_current_user_id
    user_id = get_current_user_id()
    if user_id not in _skill_loaders:
        _skill_loaders[user_id] = SkillLoader()
    return _skill_loaders[user_id]


@tool
def load_skill(name: str) -> str:
    """Load a specific skill module to gain expert knowledge for your current
    task. Call this AFTER list_skills() when you find a relevant skill.

    WHEN to use load_skill():
    - After list_skills() shows a skill relevant to your task. For example,
      if "langgraph" appears in the skill list and you are building a
      LangGraph project, call load_skill("langgraph").
    - Before starting implementation in a domain where you are not an expert.
      Skills provide patterns, anti-patterns, and best practices.
    - When you want canonical code templates instead of inventing approaches.

    CONCRETE EXAMPLES:
    - list_skills() returns "langgraph" -> load_skill("langgraph") to get
      LangGraph state graph patterns, node design, and conditional edges.
    - list_skills() returns "python" -> load_skill("python") to get coding
      standards, project structure conventions, and type hint patterns.

    BENEFIT: The skill content is injected into your response as XML-tagged
    expert knowledge. You can then apply proven patterns instead of guessing.

    Args:
        name: Skill name from list_skills() (e.g., "langgraph", "python")

    Returns:
        Skill content wrapped in <skill> tags for use in the conversation
    """
    return get_skill_loader().load(name)


@tool
def list_skills() -> str:
    """List all available specialized knowledge modules (skills). ALWAYS call
    this FIRST before tackling a task in an unfamiliar domain.

    WHEN to use list_skills():
    - At the START of any task involving a specific technology, framework,
      or domain (e.g., LangGraph, FastAPI, React, database design).
    - Before writing code in an unfamiliar library — skills contain patterns,
      best practices, and templates that save time and prevent mistakes.
    - When you are unsure about the best approach — skills may contain
      canonical patterns for common problems.

    CONCRETE EXAMPLES:
    - User asks for a LangGraph project -> list_skills() to check for
      a "langgraph" skill, then load_skill("langgraph") if available.
    - User asks for Python coding standards -> list_skills() to check for
      a "python" skill with code style and project layout guidance.

    BENEFIT: Skills inject expert domain knowledge directly into your context.
    Instead of guessing at patterns, you follow proven templates.

    Returns:
        List of available skill names and their descriptions
    """
    return get_skill_loader().list_all()


@tool
def reload_skills() -> str:
    """Reload skills from directory.

    Returns:
        Count of skills loaded
    """
    return get_skill_loader().reload()