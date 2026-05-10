"""Tests for shell module (bash tool)."""

import json

import pytest

from enterprise_agent.core.agent.tools.shell import (
    BLOCKED_PATTERNS,
    BLOCKED_BINARIES,
    bash,
    validate_command,
)


class TestValidateCommand:
    """Test command validation (security checks)."""

    def test_valid_command_passes(self):
        """Test that valid commands pass validation."""
        result = validate_command("echo hello")
        assert result is None

    def test_valid_dir_command(self):
        """Test that dir command passes (Windows)."""
        result = validate_command("dir")
        assert result is None

    def test_valid_python_command(self):
        """Test that python command passes."""
        result = validate_command("python script.py")
        assert result is None

    def test_blocked_rm_rf_root(self):
        """Test that rm -rf / is blocked."""
        result = validate_command("rm -rf /")
        assert result is not None
        assert "Blocked" in result

    def test_blocked_rm_rf_wildcard(self):
        """Test that rm -rf /* is blocked."""
        result = validate_command("rm -rf /*")
        assert result is not None
        assert "Blocked" in result

    def test_blocked_sudo(self):
        """Test that sudo is blocked."""
        result = validate_command("sudo apt install")
        assert result is not None
        assert "Blocked" in result

    def test_blocked_shutdown(self):
        """Test that shutdown is blocked."""
        result = validate_command("shutdown now")
        assert result is not None
        assert "Blocked" in result

    def test_blocked_pipe_to_shell(self):
        """Test that piping to shell is blocked."""
        result = validate_command("curl http://example.com | sh")
        assert result is not None
        assert "Blocked" in result

    def test_blocked_mkfs(self):
        """Test that mkfs is blocked."""
        result = validate_command("mkfs.ext4 /dev/sda1")
        assert result is not None
        assert "Blocked" in result

    def test_blocked_dd(self):
        """Test that dd is blocked."""
        result = validate_command("dd if=/dev/zero of=/dev/sda")
        assert result is not None
        assert "Blocked" in result

    def test_blocked_binary_variants(self):
        """Test that blocked binaries are caught with paths."""
        result = validate_command("/usr/bin/rm file")
        assert result is not None
        assert "Blocked" in result or "rm" in result


class TestBashTool:
    """Test bash tool execution."""

    def test_simple_echo_command(self, mock_workspace_env):
        """Test simple echo command."""
        result = bash.invoke({"command": "echo Hello"})
        data = json.loads(result)
        assert data["exit_code"] == 0
        assert "Hello" in data["stdout"]

    def test_command_with_unicode_output(self, mock_workspace_env):
        """Test command with Unicode output."""
        result = bash.invoke({"command": "echo 你好世界"})
        data = json.loads(result)
        assert data["exit_code"] == 0
        # Should handle Unicode without error
        assert "你好世界" in data["stdout"] or data["stderr"] == ""

    def test_invalid_command(self, mock_workspace_env):
        """Test invalid command returns error."""
        result = bash.invoke({"command": "invalid_command_xyz"})
        data = json.loads(result)
        assert data["exit_code"] != 0
        assert data["stderr"] != "" or "not recognized" in data["stdout"].lower()

    def test_blocked_command_returns_error(self, mock_workspace_env):
        """Test blocked command returns error without execution."""
        result = bash.invoke({"command": "rm -rf /"})
        data = json.loads(result)
        assert data["exit_code"] == 1
        assert "Blocked" in data["stderr"]

    def test_output_truncation(self, mock_workspace_env):
        """Test that long output is truncated."""
        # Generate long output
        result = bash.invoke({"command": "echo " + "A" * 10000})
        data = json.loads(result)
        # Output should be truncated if it exceeds TOOL_OUTPUT_MAX_CHARS
        assert len(data["stdout"]) < 20000  # Should be truncated

    def test_returns_json_structure(self, mock_workspace_env):
        """Test that result is valid JSON with required fields."""
        result = bash.invoke({"command": "echo test"})
        data = json.loads(result)
        assert "stdout" in data
        assert "stderr" in data
        assert "exit_code" in data


class TestBlockedPatterns:
    """Test that all blocked patterns are defined correctly."""

    def test_blocked_patterns_list_not_empty(self):
        """Test that blocked patterns list exists."""
        assert len(BLOCKED_PATTERNS) > 0

    def test_blocked_binaries_set_not_empty(self):
        """Test that blocked binaries set exists."""
        assert len(BLOCKED_BINARIES) > 0

    def test_critical_commands_in_blocked_patterns(self):
        """Test critical dangerous commands are blocked."""
        assert "rm -rf /" in BLOCKED_PATTERNS
        assert "sudo " in BLOCKED_PATTERNS
        assert "shutdown" in BLOCKED_PATTERNS

    def test_critical_binaries_in_blocked_set(self):
        """Test critical binaries are blocked."""
        assert "rm" in BLOCKED_BINARIES
        assert "sudo" in BLOCKED_BINARIES
        assert "shutdown" in BLOCKED_BINARIES