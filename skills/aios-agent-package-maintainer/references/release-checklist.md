# aios-agent release checklist

## Pre-release

1. Confirm target version number.
2. Update `pyproject.toml` version.
3. Add a new dated entry to `CHANGELOG.md` with Added/Changed/Fixed bullets.
4. Ensure README examples and install instructions still match the package API.

## Validation

1. Run unit tests: `pytest tests/unit -v`
2. Run lint/type checks if configured for the package.
3. Build artifacts: `python -m build`
4. Verify artifacts exist in `dist/`.

## Publish

1. Confirm index target (PyPI or TestPyPI).
2. Confirm credentials/token are configured.
3. Publish only on explicit user request.
4. Record package version, commit SHA, and publish target in PR/release notes.
