# Platform Changelog

## platform-2026.02.18.1 (2026-02-18)

### Version bumps

- `app-tentacle`: `0.1.1` -> `0.1.2` (patch)

### Included changes

- `app-tentacle` (patch): Use flux-agent in Tentacle production images and align app image metadata to flux-* repositories [`20260218061000-app-tentacle-patch-use-flux-agent-and-flux-image-metadata.yaml`]

## platform-2026.02.17.1 (2026-02-17)

### Version bumps

- `app-inkpass`: `0.1.0` -> `0.1.1` (patch)
- `app-mimic`: `0.1.0` -> `0.1.1` (patch)
- `app-tentacle`: `0.1.0` -> `0.1.1` (patch)
- `pkg-flux-agent`: `0.1.0` -> `1.0.0` (major)
- `pkg-fluxos-stripe`: `0.1.0` -> `1.0.0` (major)
- `pkg-inkpass-sdk-python`: `0.1.0` -> `0.1.1` (patch)

### Included changes

- `app-inkpass` (patch): Update InkPass defaults and Stripe integration references for the FluxOS rebrand [`20260216121000-app-inkpass-patch-fluxos-rebrand.yaml`]
- `app-mimic` (patch): Update Mimic provider setup copy and Stripe integration imports for FluxOS branding [`20260216121010-app-mimic-patch-fluxos-rebrand.yaml`]
- `pkg-fluxos-stripe` (major): Rename shared Stripe package from aios-stripe/aios_stripe to fluxos-stripe/fluxos_stripe [`20260216121020-pkg-fluxos-stripe-major-rename-package.yaml`]
- `pkg-inkpass-sdk-python` (patch): Refresh package metadata to reflect FluxOS contributor naming [`20260216121030-pkg-inkpass-sdk-python-patch-update-metadata.yaml`]
- `pkg-flux-agent` (major): Rename the agent package distribution and Python import path from aios-agent/aios_agent to flux-agent/flux_agent [`20260216195500-pkg-flux-agent-major-rename-package.yaml`]
- `app-tentacle` (patch): Update Tentacle flux runtime integration to import flux_agent instead of aios_agent [`20260216195510-app-tentacle-patch-update-flux-agent-imports.yaml`]
