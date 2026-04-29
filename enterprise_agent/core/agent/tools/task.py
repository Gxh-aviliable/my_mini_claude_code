from langchain_core.tools import tool
from typing import List, Dict


@tool
def todo_update(items: List[Dict]) -> str:
    """Update todo list with status tracking.

    Args:
        items: List of todo items with 'content', 'status', and 'activeForm' fields

    Returns:
        Rendered todo list string
    """
    validated = []
    in_progress_count = 0

    for i, item in enumerate(items):
        content = str(item.get("content", "")).strip()
        status = str(item.get("status", "pending")).lower()
        active_form = str(item.get("activeForm", "")).strip()

        # Validation
        if not content:
            raise ValueError(f"Item {i}: content required")
        if status not in ("pending", "in_progress", "completed"):
            raise ValueError(f"Item {i}: invalid status '{status}'")
        if not active_form:
            raise ValueError(f"Item {i}: activeForm required")

        if status == "in_progress":
            in_progress_count += 1

        validated.append({
            "content": content,
            "status": status,
            "activeForm": active_form
        })

    # Constraints
    if len(validated) > 20:
        raise ValueError("Maximum 20 todos allowed")
    if in_progress_count > 1:
        raise ValueError("Only one in_progress item allowed at a time")

    # Render result
    lines = []
    for item in validated:
        marker = {
            "completed": "[x]",
            "in_progress": "[>",
            "pending": "[ ]"
        }.get(item["status"], "[?]")
        suffix = f" <- {item['activeForm']}" if item["status"] == "in_progress" else ""
        lines.append(f"{marker} {item['content']}{suffix}")

    done_count = sum(1 for t in validated if t["status"] == "completed")
    lines.append(f"\n({done_count}/{len(validated)} completed)")

    return "\n".join(lines)