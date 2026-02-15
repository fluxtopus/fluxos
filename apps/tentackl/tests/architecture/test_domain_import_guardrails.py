from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


BLOCKED_PREFIXES = (
    "src.interfaces",
    "src.api",
    "src.application",
    "src.infrastructure",
    "src.services",
    "src.task",
    "src.execution",
    "src.state",
    "src.memory",
)

# Transitional shims allowed while canonical domain entities are extracted.
ALLOWED_EXCEPTIONS = {
    "domain/tasks/models.py": {"src.domain.tasks.models"},
    "domain/memory/models.py": {"src.domain.memory.models"},
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


def _matches_prefix(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


def test_domain_import_guardrails() -> None:
    src_root = Path(__file__).resolve().parents[3] / "src"
    domain_root = src_root / "domain"
    violations: list[str] = []

    for file_path in domain_root.rglob("*.py"):
        if "__pycache__" in file_path.parts:
            continue

        rel = file_path.relative_to(src_root).as_posix()
        current_module = _module_path_from_file(src_root, file_path)
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        allowed_for_file = ALLOWED_EXCEPTIONS.get(rel, set())

        for imported in _iter_imports(current_module, tree):
            blocked = any(_matches_prefix(imported, prefix) for prefix in BLOCKED_PREFIXES)
            if not blocked:
                continue
            allowed = any(_matches_prefix(imported, prefix) for prefix in allowed_for_file)
            if not allowed:
                violations.append(f"{rel} -> {imported}")

    assert not violations, (
        "Domain import guardrail violations detected:\n"
        + "\n".join(f"- {entry}" for entry in sorted(set(violations)))
    )
