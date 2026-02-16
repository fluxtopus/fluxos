# flux-agent release checklist

## Pre-release

1. Confirm intended bump (`patch|minor|major`) and behavior impact.
2. Add/update `.changes/*.yaml` note for `pkg-flux-agent`.
3. Update `packages/flux-agent/CHANGELOG.md` when package-level release notes are required.
4. Ensure README examples and install instructions still match the API.

## Validation

1. Run unit tests: `pytest tests/unit -v` (from `packages/flux-agent`).
2. Run lint/type checks if configured.
3. Validate version sync:
   - `./scripts/release/check-version-sync.sh --config release/components.yaml --manifest manifest.yaml`
4. Build artifacts:
   - `./scripts/publish-python-packages.sh --build-only --package flux-agent`

## Release and Publish

1. Confirm generated release PR includes `pkg-flux-agent` bump and `manifest.yaml` update.
2. Merge release PR.
3. Approve `Publish Release` environment gate.
4. Confirm publish target/index and credentials are configured.
5. Verify resulting tag `pkg-flux-agent@x.y.z` and archive manifest artifact.

## Manual Approval Points

1. PR review and merge are manual.
2. GitHub `release` environment approval is manual.
3. Post-publish verification (artifacts/tags) is manual.

## Rollback

1. Identify prior stable platform tag and manifest.
2. Restore `pkg-flux-agent` version as needed.
3. Regenerate manifest and re-run sync validation.
4. Merge rollback PR and run approved publish flow.
