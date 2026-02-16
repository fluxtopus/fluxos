#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from _common import component_map, load_json, load_yaml, resolve_component_name, version_source_files

VALID_BUMPS = {"patch", "minor", "major"}


def git_changed_note_files(base: str, head: str, notes_dir: str) -> list[str]:
    cmd = ["git", "diff", "--name-only", base, head, "--", f"{notes_dir}/"]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def parse_note(note_path: Path) -> dict[str, Any]:
    data = load_yaml(note_path)
    if not isinstance(data, dict):
        raise ValueError("note must be a YAML object")

    required = ["component", "bump", "summary"]
    for field in required:
        if field not in data or not str(data[field]).strip():
            raise ValueError(f"missing required field: {field}")

    bump = str(data["bump"]).strip()
    if bump not in VALID_BUMPS:
        raise ValueError(f"invalid bump '{bump}' (allowed: patch|minor|major)")

    return {
        "component": str(data["component"]).strip(),
        "bump": bump,
        "summary": str(data["summary"]).strip(),
    }


def component_requires_release_note(
    component: dict[str, Any],
    changed_files: list[str],
) -> bool:
    exempt_globs = set(version_source_files(component))
    if component.get("changelog"):
        exempt_globs.add(str(component["changelog"]))

    for rel_path in changed_files:
        if any(fnmatch(rel_path, pattern) for pattern in exempt_globs):
            continue
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate that changed components have release notes")
    parser.add_argument("--config", required=True)
    parser.add_argument("--changed", required=True, help="JSON output of detect_components.py")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--changes-dir", default=".changes")
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    config = load_yaml(repo_root / args.config)
    changed = load_json(Path(args.changed))

    component_names = set(component_map(config).keys())
    components = component_map(config)
    changed_components = set(changed.get("components", []))
    changed_component_files: dict[str, list[str]] = changed.get("component_files", {})

    required_components = {
        name
        for name in changed_components
        if component_requires_release_note(components[name], changed_component_files.get(name, []))
    }

    if not required_components:
        print("No component changes detected; release notes are not required.")
        return

    note_files = git_changed_note_files(args.base, args.head, args.changes_dir)
    if not note_files and not args.allow_empty:
        print("Changed components detected but no release notes were added in .changes/")
        print(f"Changed components: {', '.join(sorted(required_components))}")
        raise SystemExit(1)

    noted_components: set[str] = set()
    errors: list[str] = []

    for rel_path in note_files:
        if not rel_path.endswith((".yaml", ".yml")):
            continue
        if Path(rel_path).name.startswith("_"):
            continue

        note_path = repo_root / rel_path
        if not note_path.exists():
            # Deleted notes do not satisfy PR requirements.
            continue

        try:
            note = parse_note(note_path)
            component_name = resolve_component_name(config, note["component"])
            if component_name not in component_names:
                raise ValueError(f"unknown component: {note['component']}")
            noted_components.add(component_name)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{rel_path}: {exc}")

    missing = sorted(required_components - noted_components)
    if missing:
        errors.append(
            "Missing release notes for changed components: " + ", ".join(missing)
        )

    if errors:
        print("Release-note validation failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print(
        "Release-note validation passed for components: "
        + ", ".join(sorted(required_components))
    )


if __name__ == "__main__":
    main()
