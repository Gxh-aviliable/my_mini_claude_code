"""Background task management tools.

Provides tools for running long-running commands in background threads
and checking their status later.
"""

from langchain_core.tools import tool
from typing import Optional
from pathlib import Path
import subprocess
import threading
import uuid
from queue import Queue


class BackgroundManager:
    """Manages background task execution.

    Tasks run in separate threads, results stored in memory.
    Notifications queue for completed task alerts.
    """

    def __init__(self, workdir: Path = None):
        self.workdir = workdir or Path.cwd()
        self.tasks: dict = {}
        self.notifications: Queue = Queue()

    def run(self, command: str, timeout: int = 120) -> str:
        """Start a background task.

        Args:
            command: Shell command to run
            timeout: Maximum execution time in seconds

        Returns:
            Task ID and status message
        """
        task_id = str(uuid.uuid4())[:8]
        self.tasks[task_id] = {
            "status": "running",
            "command": command,
            "result": None,
            "timeout": timeout
        }

        # Start execution thread
        thread = threading.Thread(
            target=self._execute,
            args=(task_id, command, timeout),
            daemon=True
        )
        thread.start()

        return f"Background task {task_id} started: {command[:80]}..."

    def _execute(self, task_id: str, command: str, timeout: int) -> None:
        """Execute command in thread."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workdir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            output = (result.stdout + result.stderr).strip()
            self.tasks[task_id].update({
                "status": "completed",
                "result": output[:50000] or "(no output)"
            })
        except subprocess.TimeoutExpired:
            self.tasks[task_id].update({
                "status": "error",
                "result": f"Timeout after {timeout} seconds"
            })
        except Exception as e:
            self.tasks[task_id].update({
                "status": "error",
                "result": str(e)
            })

        # Send notification
        self.notifications.put({
            "task_id": task_id,
            "status": self.tasks[task_id]["status"],
            "result": self.tasks[task_id]["result"][:500]
        })

    def check(self, task_id: Optional[str] = None) -> str:
        """Check background task status.

        Args:
            task_id: Specific task ID, or None to list all

        Returns:
            Task status and result
        """
        if task_id:
            task = self.tasks.get(task_id)
            if not task:
                return f"Unknown task: {task_id}"
            status = task["status"]
            result = task.get("result") or "(running)"
            return f"[{status}] {result}"
        else:
            # List all tasks
            if not self.tasks:
                return "No background tasks."

            lines = []
            for tid, task in self.tasks.items():
                status = task["status"]
                cmd_preview = task["command"][:60]
                lines.append(f"{tid}: [{status}] {cmd_preview}")
            return "\n".join(lines)

    def drain_notifications(self) -> list:
        """Drain all pending notifications.

        Returns:
            List of notification dicts
        """
        notifications = []
        while not self.notifications.empty():
            notifications.append(self.notifications.get_nowait())
        return notifications


# Global instance
_bg_manager: Optional[BackgroundManager] = None


def get_background_manager() -> BackgroundManager:
    """Get or create BackgroundManager instance."""
    if _bg_manager is None:
        _bg_manager = BackgroundManager()
    return _bg_manager


# === Tool Definitions ===

@tool
def background_run(command: str, timeout: int = 120) -> str:
    """Run a command in background thread.

    Use check_background to get results later.

    Args:
        command: Shell command to execute
        timeout: Maximum execution time in seconds (default 120)

    Returns:
        Task ID and start message
    """
    return get_background_manager().run(command, timeout)


@tool
def check_background(task_id: Optional[str] = None) -> str:
    """Check background task status or list all tasks.

    Args:
        task_id: Specific task ID to check, or None to list all

    Returns:
        Task status and result, or list of all tasks
    """
    return get_background_manager().check(task_id)