from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


LEGACY_IMPORT_RULES = {
    "src.infrastructure.evaluations.prompt_evaluation_service": {"services/prompt_evaluation_service.py"},
    "src.infrastructure.capabilities.capability_yaml_validation": {"services/capability_yaml_validation.py"},
    "src.infrastructure.agents.agent_generator_service": {"services/agent_generator_service.py"},
    "src.infrastructure.agents.agent_validation_service": {"services/agent_validation_service.py"},
    "src.services.auth": set(),
    "src.infrastructure.allowed_hosts.allowed_host_service": {"services/allowed_host_service.py"},
    "src.infrastructure.workspace.workspace_service": {"services/workspace_service.py"},
    "src.infrastructure.inbox.inbox_service": {"services/inbox"},
    "src.infrastructure.inbox.summary_service": {"services/inbox"},
    "src.infrastructure.inbox.inbox_tool_registry": {
        "services/inbox/inbox_tool_registry.py",
    },
    "src.services.inbox.tools": set(),
    "src.services.google.calendar_assistant": set(),
    "src.infrastructure.capabilities.capability_embedding_service": {
        "services/embedding/capability_embedding_service.py",
    },
    "src.infrastructure.tasks.event_publisher": {"services/task"},
    "src.infrastructure.triggers.task_trigger_registry": {"services/task"},
    # TaskService has been fully retired; no imports are allowed.
    "src.services.task.task_service": set(),
    "src.infrastructure.tasks.state_machine": {"services/task"},
    "src.infrastructure.tasks.checkpoint_manager": {"services/task"},
    "src.infrastructure.tasks.preference_learning": {"services/task"},
    "src.infrastructure.tasks.stores.redis_task_store": {
        "task",
    },
    "src.infrastructure.tasks.stores.postgres_task_store": {
        "task",
    },
    "src.infrastructure.tasks.stores.redis_preference_store": {"task"},
    "src.infrastructure.tasks.task_tree_adapter": {"task"},
    "src.infrastructure.tasks.task_tree_mapping": {"task"},
    "src.infrastructure.tasks.step_dispatcher": {"task"},
    "src.infrastructure.tasks.task_scheduler_helper": {"task"},
    "src.arrow": {"arrow", "infrastructure/flux_runtime"},
    "src.infrastructure.memory.memory_service": {"memory", "infrastructure/memory"},
}


def _module_path_from_file(src_root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(src_root)
    if rel.name == "__init__.py":
        rel = rel.parent
    return ".".join(rel.with_suffix("").parts)


def _resolve_import(current_module: str, node: ast.ImportFrom) -> str | None:
    if node.module is None and node.level == 0:
        return None

    module = node.module or ""
    if node.level:
        rel = "." * node.level + module
        try:
            return importlib.util.resolve_name(rel, package=current_module)
        except (ImportError, ValueError):
            return None

    return module


def _iter_imports(current_module: str, tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_import(current_module, node)
            if resolved:
                imports.add(resolved)
    return imports


def _allowed_for_rule(rel_file: Path, allowed_paths: set[str]) -> bool:
    rel_posix = rel_file.as_posix()
    return any(
        rel_posix == prefix or rel_posix.startswith(prefix)
        for prefix in allowed_paths
    )


def test_legacy_import_guardrails() -> None:
    src_root = Path(__file__).resolve().parents[3] / "src"
    violations: list[str] = []

    for file_path in src_root.rglob("*.py"):
        if "__pycache__" in file_path.parts:
            continue

        rel = file_path.relative_to(src_root)
        current_module = _module_path_from_file(src_root, file_path)
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for imported in _iter_imports(current_module, tree):
            for legacy_prefix, allowed_paths in LEGACY_IMPORT_RULES.items():
                if imported == legacy_prefix or imported.startswith(f"{legacy_prefix}."):
                    if not _allowed_for_rule(rel, allowed_paths):
                        violations.append(f"{rel.as_posix()} -> {imported}")

    assert not violations, (
        "Legacy import guardrail violations detected:\n"
        + "\n".join(f"- {entry}" for entry in sorted(set(violations)))
    )
