---
name: fluxos-agent-package-maintainer
description: Maintain and release the flux-agent Python package with consistent versioning and change tracking. Use when updating package code, preparing a release, publishing to PyPI/TestPyPI, or auditing what changed between versions.
---

# Flux Agent Package Maintainer

Use this skill when a task touches `packages/flux-agent` versioning, changelog, packaging, or publishing.

## Sources Of Truth

- Package root: `packages/flux-agent`
- Version source: `packages/flux-agent/pyproject.toml`
- Runtime version: `packages/flux-agent/flux_agent/version.py`
- Package changelog: `packages/flux-agent/CHANGELOG.md`
- Platform manifest snapshot: `manifest.yaml`
- Release plan metadata: `release/latest-release-plan.json`

## Required PR Metadata

If a PR changes `packages/flux-agent/**`, add one note in `.changes/`:

```yaml
component: pkg-flux-agent
bump: patch
summary: "Short user-visible change summary"
```

Use bump values: `patch|minor|major`.

## Standard Workflow

1. Inspect package changes (`git diff -- packages/flux-agent`).
2. Add/update tests and docs for behavior changes.
3. Add `.changes/*.yaml` note for `pkg-flux-agent`.
4. Validate version consistency:
   - `./scripts/release/check-version-sync.sh --config release/components.yaml --manifest manifest.yaml`
5. Build package artifacts when needed:
   - `./scripts/publish-python-packages.sh --build-only --package flux-agent`
6. Publish only via approved release workflow after merge.

## How To Cut A Release

1. Merge PR(s) with valid `.changes` notes.
2. Review generated release PR (`chore(release): prepare ...`).
3. Merge release PR.
4. Approve `Publish Release` workflow environment gate.
5. Confirm `pkg-flux-agent@x.y.z` tag and manifest artifact.

## Automation vs Manual

Automated:

- Release PR generation from `.changes` notes (`Prepare Release PR` workflow).
- Version bumping, manifest regeneration, note archiving, and changelog update.
- Publish/build + tag creation after release PR merge (`Publish Release` workflow).

Manual:

- Review and merge release PR.
- Approve `release` environment in GitHub Actions.
- Confirm publish outputs and tags.

Optional CLI automation for developer-created PRs:

```bash
git checkout -b <branch>
git add -A
git commit -m "chore(release): ... "
git push -u origin <branch>
gh pr create --fill
```

## How To Roll Back

1. Identify target platform tag and load its `manifest.yaml` artifact.
2. Restore `pkg-flux-agent` version from that manifest.
3. Run:
   - `./scripts/release/update-manifest.sh --config release/components.yaml --output manifest.yaml`
   - `./scripts/release/check-version-sync.sh --config release/components.yaml --manifest manifest.yaml`
4. Merge rollback PR and run publish workflow with approval.

## Release Checklist

Use `references/release-checklist.md`.

Always enforce:

- Version bump + changelog updates are part of the same change set.
- No publish before tests/build pass.
- No release without explicit approval.
