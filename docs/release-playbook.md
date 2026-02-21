# Release Playbook

This repository uses independent component SemVer and a root platform manifest.

## Policy

- Each app/package has its own SemVer stream.
- `manifest.yaml` snapshots all tracked component versions per platform release.
- Bump levels are explicit in `.changes/*.yaml` (`patch`, `minor`, `major`).
- Release cadence: on every merge to `main` that includes pending `.changes` notes.
- App bump trigger: any PR that changes a tracked component and should ship must include one note in `.changes/`.

## Sources Of Truth

- Apps:
  - `apps/tentacle/VERSION`
  - `apps/inkpass/VERSION`
  - `apps/mimic/VERSION`
- Packages (existing sources):
  - `pyproject.toml`, `package.json`, `setup.py`, `__version__` files as defined in `release/components.yaml`
- Platform snapshot:
  - `manifest.yaml`
- App image repositories:
  - Defined in `release/components.yaml` via `image_repository`
  - Current naming convention uses `flux-` prefix (for example `ghcr.io/fluxtopus/flux-tentacle`)

## Release Notes Contract (`.changes`)

Each PR touching a tracked component must add a YAML note.

Example:

```yaml
component: app-tentacle
bump: patch
summary: "Fix timeout handling for long-running workflows"
```

Rules:

- File naming: `YYYYMMDDHHMMSS-<component>-<slug>.yaml`
- `component`: component name from `release/components.yaml` (or scope alias)
- `bump`: `patch|minor|major`
- `summary`: user-visible change summary

Lifecycle:

1. Notes are added in `.changes/` by PRs.
2. Release PR consumes all pending notes.
3. Consumed notes move to `releases/notes/<platform-release>/`.

## Build Automation Scripts

- `scripts/release/detect-components.sh`: compute impacted components from git diff
- `scripts/release/validate-change-notes.sh`: enforce note presence/format for changed components
- `scripts/release/compute-bumps-from-changes.sh`: build bump plan from `.changes` notes
- `scripts/release/bump-versions.sh`: apply planned version bumps
- `scripts/release/bump-component.sh`: manually bump a selected component safely
- `scripts/release/update-manifest.sh`: regenerate `manifest.yaml`
- `scripts/release/check-version-sync.sh`: validate version sources + manifest alignment
- `scripts/release/finalize-release.sh`: update changelog, archive notes, write release plan
- `scripts/release/tag-release.sh`: create immutable component/platform tags

## CI/CD Gates

PR checks (`.github/workflows/ci.yml`):

- changed component => release note required
- version sync validation required

Main workflows:

1. `release-on-main.yml`
   - Computes bump plan from `.changes`
   - Applies version bumps
   - Regenerates `manifest.yaml`
   - Updates `releases/CHANGELOG.md`
   - Archives consumed notes
   - Opens release PR
2. `publish-release.yml`
   - Runs after release PR merge commit
   - Requires environment approval (`release`)
   - Builds/publishes changed artifacts:
     - app container images to GHCR (`ghcr.io/fluxtopus/flux-*`)
     - Python packages to PyPI
     - TypeScript packages to npm
   - Creates immutable tags
   - Uploads `manifest.yaml` and release metadata artifact

## Tagging And Traceability

- Component tag format: `component-name@x.y.z`
- Platform tag format: `platform-YYYY.MM.DD.N`
- `manifest.yaml` includes:
  - `schema_version`
  - `generated_at`
  - `platform_release`
  - `git_sha`
  - per-component version source files + digest

## How To Cut A Release

1. Merge PRs that include valid `.changes/*.yaml` files.
2. Wait for `Prepare Release PR` workflow to open a release PR.
3. Review and merge the release PR.
4. Approve `Publish Release` environment gate.
5. Confirm artifacts/tags and archive outputs.

## How To Roll Back

1. Select target `platform-*` tag and read its `manifest.yaml` artifact.
2. Identify component versions that must be restored.
3. Revert to those versions by checking out the matching release commit or applying targeted `bump-component.sh` changes.
4. Re-run:
   - `./scripts/release/update-manifest.sh --config release/components.yaml --output manifest.yaml`
   - `./scripts/release/check-version-sync.sh --config release/components.yaml --manifest manifest.yaml`
5. Merge rollback PR and run publish workflow with approval.

## Bootstrap (One-Time)

For first-time rollout:

- `./scripts/release/bootstrap-release-metadata.sh --config release/components.yaml --manifest manifest.yaml --write`
