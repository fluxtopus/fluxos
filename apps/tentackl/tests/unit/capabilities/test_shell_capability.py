"""
Unit tests for SEC-006: Hardened shell capability

Tests cover:
1. Required non-empty allowed_commands whitelist
2. create_subprocess_exec usage (no shell injection)
3. Interpreter whitelist for execute_script
4. Expanded forbidden patterns blocklist
5. Command validation (whitelist enforcement, forbidden patterns, sudo)
6. Source code verification (no create_subprocess_shell)
"""

import asyncio
import os
import inspect
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.capabilities.shell_capability import (
    ShellExecutor,
    ShellCapabilityMethods,
    CommandResult,
)


# ─── Helpers ────────────────────────────────────────────────────────────

def make_config(**overrides):
    """Create a valid ShellExecutor config with required allowed_commands."""
    base = {
        "allowed_commands": ["ls", "cat", "echo", "grep", "bash", "python3"],
        "working_dir": "/tmp",
        "capture_performance": False,
    }
    base.update(overrides)
    return base


# ─── 1. Required non-empty allowed_commands ─────────────────────────────

class TestAllowedCommandsRequired:

    def test_empty_allowed_commands_raises(self):
        """Empty allowed_commands list must raise ValueError."""
        with pytest.raises(ValueError, match="non-empty 'allowed_commands' whitelist"):
            ShellExecutor({"allowed_commands": []})

    def test_missing_allowed_commands_raises(self):
        """Omitting allowed_commands entirely must raise ValueError."""
        with pytest.raises(ValueError, match="non-empty 'allowed_commands' whitelist"):
            ShellExecutor({})

    def test_non_empty_allowed_commands_ok(self):
        """Non-empty allowed_commands must be accepted."""
        executor = ShellExecutor(make_config(allowed_commands=["ls"]))
        assert executor.allowed_commands == ["ls"]


# ─── 2. create_subprocess_exec (source code verification) ───────────────

class TestNoSubprocessShell:

    def test_source_code_uses_exec_not_shell(self):
        """Verify source code uses create_subprocess_exec, not create_subprocess_shell."""
        source = inspect.getsource(ShellExecutor)
        assert "create_subprocess_exec" in source, "Must use create_subprocess_exec"
        assert "create_subprocess_shell" not in source, "Must NOT use create_subprocess_shell"


# ─── 3. Interpreter whitelist ────────────────────────────────────────────

class TestInterpreterWhitelist:

    def test_safe_interpreters_defined(self):
        """SAFE_INTERPRETERS must include common safe interpreters."""
        expected = {"bash", "sh", "python3", "python", "node", "ruby", "perl"}
        assert ShellExecutor.SAFE_INTERPRETERS == expected

    @pytest.mark.asyncio
    async def test_unsafe_interpreter_rejected(self):
        """Interpreter not in SAFE_INTERPRETERS must be rejected."""
        executor = ShellExecutor(make_config())
        with pytest.raises(ValueError, match="Interpreter '/bin/evil' is not allowed"):
            await executor.execute_script("echo hi", interpreter="/bin/evil")

    @pytest.mark.asyncio
    async def test_path_traversal_interpreter_rejected(self):
        """Path-based interpreter (e.g. /usr/bin/python3) must be rejected."""
        executor = ShellExecutor(make_config())
        with pytest.raises(ValueError, match="is not allowed"):
            await executor.execute_script("echo hi", interpreter="/usr/bin/python3")

    @pytest.mark.asyncio
    async def test_empty_interpreter_rejected(self):
        executor = ShellExecutor(make_config())
        with pytest.raises(ValueError, match="is not allowed"):
            await executor.execute_script("echo hi", interpreter="")


# ─── 4. Expanded forbidden patterns ─────────────────────────────────────

class TestForbiddenPatterns:

    def test_default_patterns_expanded(self):
        """Default forbidden patterns must have significantly more than 5 entries."""
        patterns = ShellExecutor.DEFAULT_FORBIDDEN_PATTERNS
        assert len(patterns) > 20, f"Expected >20 forbidden patterns, got {len(patterns)}"

    def test_original_5_patterns_still_present(self):
        """Original 5 patterns must still be in the defaults."""
        patterns = ShellExecutor.DEFAULT_FORBIDDEN_PATTERNS
        for p in ["rm -rf /", ":(){ :|:& };:", "dd if=", "mkfs", "format"]:
            assert p in patterns, f"Original pattern '{p}' missing"

    def test_reverse_shell_patterns_present(self):
        """Reverse shell patterns must be blocked."""
        patterns = ShellExecutor.DEFAULT_FORBIDDEN_PATTERNS
        for p in ["/dev/tcp/", "nc -l", "bash -i"]:
            assert p in patterns, f"Reverse shell pattern '{p}' missing"

    def test_privilege_escalation_patterns_present(self):
        patterns = ShellExecutor.DEFAULT_FORBIDDEN_PATTERNS
        for p in ["chmod 777", "chown root"]:
            assert p in patterns

    def test_credential_theft_patterns_present(self):
        patterns = ShellExecutor.DEFAULT_FORBIDDEN_PATTERNS
        for p in ["/etc/shadow", "/etc/passwd", ".ssh/"]:
            assert p in patterns

    def test_container_escape_patterns_present(self):
        patterns = ShellExecutor.DEFAULT_FORBIDDEN_PATTERNS
        for p in ["nsenter", "chroot"]:
            assert p in patterns


# ─── 5. Command validation ──────────────────────────────────────────────

class TestCommandValidation:

    def test_allowed_command_passes(self):
        executor = ShellExecutor(make_config())
        # Should not raise
        executor._validate_command("ls -la /tmp")

    def test_disallowed_command_rejected(self):
        executor = ShellExecutor(make_config(allowed_commands=["ls"]))
        with pytest.raises(ValueError, match="not in allowed list"):
            executor._validate_command("curl http://evil.com")

    def test_forbidden_pattern_blocks_allowed_command(self):
        """Even if 'rm' is in allowed_commands, 'rm -rf /' is still blocked."""
        executor = ShellExecutor(make_config(allowed_commands=["rm"]))
        with pytest.raises(ValueError, match="Forbidden command pattern"):
            executor._validate_command("rm -rf /")

    def test_sudo_blocked_by_default(self):
        executor = ShellExecutor(make_config(allowed_commands=["sudo", "ls"]))
        with pytest.raises(ValueError, match="Sudo commands are not allowed"):
            executor._validate_command("sudo ls")

    def test_sudo_allowed_when_configured(self):
        executor = ShellExecutor(make_config(
            allowed_commands=["sudo", "ls"],
            allow_sudo=True
        ))
        # Should not raise
        executor._validate_command("sudo ls")

    def test_empty_command_rejected(self):
        executor = ShellExecutor(make_config())
        with pytest.raises(ValueError, match="Empty command is not allowed"):
            executor._validate_command("")

    def test_custom_forbidden_patterns(self):
        """Config can override forbidden patterns."""
        executor = ShellExecutor(make_config(
            forbidden_patterns=["my_custom_pattern"]
        ))
        with pytest.raises(ValueError, match="Forbidden command pattern"):
            executor._validate_command("ls my_custom_pattern")


# ─── 6. Integration: execute() uses exec ────────────────────────────────

class TestExecuteUsesExec:

    @pytest.mark.asyncio
    async def test_execute_calls_subprocess_exec(self):
        """execute() must call create_subprocess_exec, not shell."""
        executor = ShellExecutor(make_config(capture_performance=False))

        mock_process = AsyncMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            result = await executor.execute("echo hello")
            mock_exec.assert_called_once()
            # First positional arg should be the command name
            call_args = mock_exec.call_args
            assert call_args[0][0] == "echo"
            assert call_args[0][1] == "hello"

    @pytest.mark.asyncio
    async def test_execute_does_not_call_shell(self):
        """Ensure create_subprocess_shell is never called."""
        executor = ShellExecutor(make_config(capture_performance=False))

        mock_process = AsyncMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process), \
             patch("asyncio.create_subprocess_shell") as mock_shell:
            await executor.execute("echo hello")
            mock_shell.assert_not_called()


# ─── 7. Script execution respects both interpreter and allowed_commands ──

class TestExecuteScript:

    @pytest.mark.asyncio
    async def test_execute_script_validates_interpreter_before_execute(self):
        """Unsafe interpreter must be rejected before file is created."""
        executor = ShellExecutor(make_config())
        with pytest.raises(ValueError, match="is not allowed"):
            await executor.execute_script("echo hi", interpreter="zsh")

    @pytest.mark.asyncio
    async def test_execute_script_interpreter_must_be_in_allowed_commands(self):
        """Interpreter must also be in allowed_commands to actually run."""
        executor = ShellExecutor(make_config(allowed_commands=["ls"]))  # no bash
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # bash is safe interpreter but not in allowed_commands
            with pytest.raises(ValueError, match="not in allowed list"):
                await executor.execute_script("echo hi", interpreter="bash")


# ─── 8. ShellCapabilityMethods delegates correctly ──────────────────────

class TestShellCapabilityMethods:

    @pytest.mark.asyncio
    async def test_shell_method_returns_dict(self):
        executor = ShellExecutor(make_config(capture_performance=False))
        methods = ShellCapabilityMethods(executor)

        mock_process = AsyncMock()
        mock_process.pid = 1
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"hello\n", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await methods.shell("echo hello")
            assert result["success"] is True
            assert result["stdout"] == "hello\n"
            assert result["return_code"] == 0

    @pytest.mark.asyncio
    async def test_shell_script_rejects_bad_interpreter(self):
        executor = ShellExecutor(make_config())
        methods = ShellCapabilityMethods(executor)
        with pytest.raises(ValueError, match="is not allowed"):
            await methods.shell_script("echo hi", interpreter="/tmp/evil")


# ─── 9. File permission on script ────────────────────────────────────────

class TestScriptPermissions:

    def test_source_uses_0o700(self):
        """Script file should be created with owner-only execute (0o700)."""
        source = inspect.getsource(ShellExecutor.execute_script)
        assert "0o700" in source, "Script should use 0o700 permission"
        assert "0o755" not in source, "Script should NOT use world-readable 0o755"
