---
name: aios-agent-package-maintainer
description: Maintain and release the aios-agent Python package with consistent versioning and change tracking. Use when updating package code, preparing a release, publishing to PyPI/TestPyPI, or auditing what changed between versions.
---

# AIOS Agent Package Maintainer

## Overview

Use this skill to manage updates to `aios-agent` safely and consistently.
Always keep version, changelog, tests, and release artifacts in sync.

## Source Of Truth

- Package root: `packages/aios-agent`
- Version file: `packages/aios-agent/pyproject.toml`
- Change log: `packages/aios-agent/CHANGELOG.md`
- Package docs: `packages/aios-agent/README.md`

## Workflow

1. Confirm release intent and change scope.
2. Inspect package deltas.
3. Update version and changelog in the same change set.
4. Run package validation (tests and lint/type checks when available).
5. Build distribution artifacts.
6. Publish only when explicitly requested and credentials are configured.
7. Record release commit/tag and summary in PR notes.

## Standard Commands

Run commands from:
`packages/aios-agent`

```bash
# Inspect package changes
git log --oneline -- packages/aios-agent
git diff -- packages/aios-agent

# Run unit tests
pytest tests/unit -v

# Build package
python -m build

# Publish (if requested)
uv publish
```

## Release Checklist

Use:
`references/release-checklist.md`

Always enforce:
- Every version bump must include a matching `CHANGELOG.md` section.
- No publish step before tests/build pass.
- No release without explicit user approval.
