"""
Shell Command Capability for Tentackl

This module provides safe shell command execution capabilities for agents,
with proper sandboxing, resource limits, and security controls.
"""

import asyncio
import os
import shlex
import signal
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
import structlog
from pathlib import Path
import psutil

from ..interfaces.configurable_agent import AgentCapability
from .capability_registry import ToolDefinition

logger = structlog.get_logger(__name__)


@dataclass
class CommandResult:
    """Result of a shell command execution"""
    stdout: str
    stderr: str
    return_code: int
    duration_seconds: float
    timed_out: bool = False
    memory_peak_mb: Optional[float] = None
    cpu_percent: Optional[float] = None


class ShellExecutor:
    """Safe shell command executor with resource limits"""

    # Safe interpreters that may be used with execute_script
    SAFE_INTERPRETERS = frozenset({"bash", "sh", "python3", "python", "node", "ruby", "perl"})

    # Default forbidden patterns — covers destructive commands, fork bombs,
    # raw device access, privilege escalation, reverse shells, data exfiltration,
    # history/credential theft, and container escapes.
    DEFAULT_FORBIDDEN_PATTERNS = [
        # Destructive filesystem operations
        "rm -rf /",
        "rm -rf /*",
        "rm -rf .",
        # Fork bombs
        ":(){ :|:& };:",
        # Raw device / partition manipulation
        "dd if=",
        "mkfs",
        "format",
        "fdisk",
        "parted",
        # Privilege escalation
        "chmod 777",
        "chmod -R 777",
        "chown root",
        "setuid",
        # Reverse shells / bind shells
        "/dev/tcp/",
        "/dev/udp/",
        "nc -l",
        "ncat -l",
        "socat",
        "bash -i",
        "python -c 'import socket",
        "python3 -c 'import socket",
        # Data exfiltration
        "curl.*|.*sh",
        "wget.*|.*sh",
        "curl.*|.*bash",
        "wget.*|.*bash",
        # Credential / history theft
        "/etc/shadow",
        "/etc/passwd",
        ".bash_history",
        ".ssh/",
        # Container escape
        "nsenter",
        "mount /",
        "chroot",
        # Kernel / system manipulation
        "insmod",
        "modprobe",
        "sysctl -w",
        # Process / cgroup escape
        "unshare",
        "cgexec",
        # Environment dumping (secrets leakage)
        "printenv",
        "env | ",
        "set | ",
    ]

    def __init__(self, config: Dict[str, Any]):
        self.config = config

        # Security settings — allowed_commands MUST be provided and non-empty
        self.allowed_commands = config.get("allowed_commands", [])
        if not self.allowed_commands:
            raise ValueError(
                "ShellExecutor requires a non-empty 'allowed_commands' whitelist. "
                "Specify the exact commands agents are permitted to run."
            )
        self.forbidden_patterns = config.get("forbidden_patterns", self.DEFAULT_FORBIDDEN_PATTERNS)
        self.working_dir = config.get("working_dir", "/tmp")
        self.env_vars = config.get("env_vars", {})

        # Resource limits
        self.timeout_seconds = config.get("timeout_seconds", 60)
        self.max_memory_mb = config.get("max_memory_mb", 512)
        self.max_cpu_percent = config.get("max_cpu_percent", 100)
        self.max_output_size = config.get("max_output_size", 1024 * 1024)  # 1MB

        # Features
        self.allow_sudo = config.get("allow_sudo", False)
        self.allow_network = config.get("allow_network", True)
        self.capture_performance = config.get("capture_performance", True)
    
    def _validate_command(self, command: str) -> None:
        """Validate command against security rules"""
        # Check forbidden patterns
        for pattern in self.forbidden_patterns:
            if pattern in command:
                raise ValueError(f"Forbidden command pattern detected: {pattern}")

        # Enforce allowed_commands whitelist (always required)
        cmd_parts = shlex.split(command)
        base_cmd = cmd_parts[0] if cmd_parts else ""
        if not base_cmd:
            raise ValueError("Empty command is not allowed")
        if base_cmd not in self.allowed_commands:
            raise ValueError(f"Command '{base_cmd}' not in allowed list")

        # Check sudo
        if "sudo" in command and not self.allow_sudo:
            raise ValueError("Sudo commands are not allowed")
    
    async def execute(self, command: str, 
                     stdin: Optional[str] = None,
                     working_dir: Optional[str] = None) -> CommandResult:
        """Execute a shell command with resource limits"""
        
        # Validate command
        self._validate_command(command)
        
        # Setup working directory
        work_dir = working_dir or self.working_dir
        if not os.path.exists(work_dir):
            os.makedirs(work_dir, exist_ok=True)
        
        # Setup environment
        env = os.environ.copy()
        env.update(self.env_vars)
        
        # Performance tracking
        start_time = time.time()
        peak_memory = 0
        avg_cpu = []
        
        try:
            # Split command into args for exec (prevents shell injection)
            cmd_args = shlex.split(command)

            # Create subprocess using exec (no shell interpretation)
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=asyncio.subprocess.PIPE if stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env=env,
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            
            # Monitor process if needed
            monitor_task = None
            if self.capture_performance and process.pid:
                monitor_task = asyncio.create_task(
                    self._monitor_process(process.pid, avg_cpu)
                )
            
            # Execute with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=stdin.encode() if stdin else None),
                    timeout=self.timeout_seconds
                )
                timed_out = False
            except asyncio.TimeoutError:
                # Kill process group on timeout
                if os.name != 'nt':
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                else:
                    process.terminate()
                await asyncio.sleep(0.1)
                if process.returncode is None:
                    process.kill()
                stdout, stderr = b"", b"Command timed out"
                timed_out = True
            
            # Stop monitoring
            if monitor_task:
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
            
            # Get performance metrics
            if self.capture_performance and avg_cpu:
                peak_memory = max(avg_cpu, key=lambda x: x[1])[1] if avg_cpu else 0
                avg_cpu_percent = sum(x[0] for x in avg_cpu) / len(avg_cpu) if avg_cpu else 0
            else:
                peak_memory = None
                avg_cpu_percent = None
            
            # Decode output with size limits
            stdout_str = stdout.decode('utf-8', errors='replace')[:self.max_output_size]
            stderr_str = stderr.decode('utf-8', errors='replace')[:self.max_output_size]
            
            duration = time.time() - start_time
            
            return CommandResult(
                stdout=stdout_str,
                stderr=stderr_str,
                return_code=process.returncode if not timed_out else -1,
                duration_seconds=duration,
                timed_out=timed_out,
                memory_peak_mb=peak_memory,
                cpu_percent=avg_cpu_percent
            )
            
        except Exception as e:
            logger.error("Command execution failed", command=command, error=str(e))
            return CommandResult(
                stdout="",
                stderr=str(e),
                return_code=-1,
                duration_seconds=time.time() - start_time,
                timed_out=False
            )
    
    async def _monitor_process(self, pid: int, metrics: List[Tuple[float, float]]) -> None:
        """Monitor process resource usage"""
        try:
            process = psutil.Process(pid)
            while True:
                cpu_percent = process.cpu_percent(interval=0.1)
                memory_mb = process.memory_info().rss / 1024 / 1024
                
                metrics.append((cpu_percent, memory_mb))
                
                # Check resource limits
                if memory_mb > self.max_memory_mb:
                    logger.warning("Process exceeding memory limit", 
                                 pid=pid, memory_mb=memory_mb, limit=self.max_memory_mb)
                    process.terminate()
                    break
                
                await asyncio.sleep(0.5)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception as e:
            logger.error("Process monitoring error", error=str(e))
    
    async def execute_pipeline(self, commands: List[str]) -> List[CommandResult]:
        """Execute a pipeline of commands"""
        results = []
        for command in commands:
            result = await self.execute(command)
            results.append(result)
            if result.return_code != 0:
                break  # Stop on first failure
        return results
    
    async def execute_script(self, script_content: str,
                           interpreter: str = "bash") -> CommandResult:
        """Execute a script file with a whitelisted interpreter"""
        # Validate interpreter against safe whitelist
        if interpreter not in self.SAFE_INTERPRETERS:
            raise ValueError(
                f"Interpreter '{interpreter}' is not allowed. "
                f"Permitted interpreters: {sorted(self.SAFE_INTERPRETERS)}"
            )

        # Create temporary script file
        script_path = os.path.join(self.working_dir, f"script_{time.time()}.sh")
        try:
            with open(script_path, 'w') as f:
                f.write(script_content)
            os.chmod(script_path, 0o700)  # owner-only execute

            # Execute script — interpreter must be in allowed_commands
            return await self.execute(f"{interpreter} {script_path}")
        finally:
            # Cleanup
            if os.path.exists(script_path):
                os.remove(script_path)


class ShellCapabilityMethods:
    """Methods that will be injected into agents with shell capability"""
    
    def __init__(self, executor: ShellExecutor):
        self._executor = executor
    
    async def shell(self, command: str, **kwargs) -> Dict[str, Any]:
        """Execute a shell command"""
        result = await self._executor.execute(command, **kwargs)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.return_code,
            "success": result.return_code == 0,
            "duration": result.duration_seconds,
            "timed_out": result.timed_out
        }
    
    async def shell_pipeline(self, commands: List[str]) -> List[Dict[str, Any]]:
        """Execute a pipeline of commands"""
        results = await self._executor.execute_pipeline(commands)
        return [
            {
                "command": cmd,
                "stdout": r.stdout,
                "stderr": r.stderr,
                "return_code": r.return_code,
                "success": r.return_code == 0
            }
            for cmd, r in zip(commands, results)
        ]
    
    async def shell_script(self, script: str, interpreter: str = "bash") -> Dict[str, Any]:
        """Execute a script"""
        result = await self._executor.execute_script(script, interpreter)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.return_code,
            "success": result.return_code == 0,
            "duration": result.duration_seconds
        }
    
    async def check_command_exists(self, command: str) -> bool:
        """Check if a command exists in PATH (requires 'which' in allowed_commands)"""
        result = await self._executor.execute(f"which {command}")
        return result.return_code == 0


# Handler functions
async def shell_handler(config: Dict[str, Any]) -> ShellCapabilityMethods:
    """Create shell capability methods"""
    executor = ShellExecutor(config)
    return ShellCapabilityMethods(executor)


# Register the capability
SHELL_CAPABILITY = ToolDefinition(
    name="shell",
    description="Execute shell commands with security controls and resource limits",
    handler=shell_handler,
    config_schema={
        "type": "object",
        "properties": {
            "allowed_commands": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Required whitelist of allowed base commands (e.g. ['ls', 'cat', 'grep']). Must be non-empty."
            },
            "forbidden_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Patterns that will block command execution"
            },
            "working_dir": {
                "type": "string",
                "default": "/tmp",
                "description": "Default working directory"
            },
            "env_vars": {
                "type": "object",
                "description": "Environment variables to set"
            },
            "timeout_seconds": {
                "type": "integer",
                "default": 60,
                "description": "Command timeout in seconds"
            },
            "max_memory_mb": {
                "type": "integer",
                "default": 512,
                "description": "Maximum memory usage in MB"
            },
            "max_output_size": {
                "type": "integer",
                "default": 1048576,
                "description": "Maximum output size in bytes"
            },
            "allow_sudo": {
                "type": "boolean",
                "default": False,
                "description": "Allow sudo commands"
            },
            "capture_performance": {
                "type": "boolean",
                "default": True,
                "description": "Capture CPU and memory metrics"
            }
        }
    },
    permissions_required=["system:shell"],
    sandboxable=True,
    category=AgentCapability.CUSTOM
)