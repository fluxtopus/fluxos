from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

LAYER_ROOTS = {"domain", "application", "infrastructure", "interfaces"}

ALLOWED_LAYER_IMPORTS = {
    "domain": {"domain"},
    "application": {"application", "domain"},
    "infrastructure": {"infrastructure", "domain"},
    "interfaces": {"interfaces", "application", "domain"},
}

ALLOWLIST_PATH = Path(__file__).with_name("layered_import_allowlist.txt")


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


def _collect_layered_import_violations(src_root: Path) -> list[str]:
    violations: list[str] = []

    for file_path in src_root.rglob("*.py"):
        if "__pycache__" in file_path.parts:
            continue

        rel = file_path.relative_to(src_root)
        if not rel.parts:
            continue

        layer = rel.parts[0]
        if layer not in LAYER_ROOTS:
            continue

        current_module = _module_path_from_file(src_root, file_path)
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for imported in _iter_imports(current_module, tree):
            top_level = imported.split(".", 1)[0]
            if top_level not in LAYER_ROOTS:
                continue

            if top_level not in ALLOWED_LAYER_IMPORTS[layer]:
                violations.append(f"{current_module} -> {imported}")

    return sorted(set(violations))


def _load_allowlist() -> set[str]:
    if not ALLOWLIST_PATH.exists():
        return set()

    allowed: set[str] = set()
    for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        allowed.add(stripped)

    return allowed


def test_layered_imports_guardrail():
    src_root = Path(__file__).resolve().parents[3] / "src"
    violations = _collect_layered_import_violations(src_root)
    allowlist = _load_allowlist()

    unexpected = [violation for violation in violations if violation not in allowlist]
    stale = [violation for violation in allowlist if violation not in violations]

    assert not unexpected, (
        "Layered import violations detected:\n"
        + "\n".join(f"- {violation}" for violation in unexpected)
        + "\nUpdate allowlist: apps/tentackl/tests/architecture/layered_import_allowlist.txt"
    )
    assert not stale, (
        "Allowlist contains stale entries (clean these up):\n"
        + "\n".join(f"- {violation}" for violation in stale)
    )
