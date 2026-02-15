# ADR-007: Adopt json-render and Serve Static Websites as Artifacts

## Status
Accepted

## Date
2026-02-14

## Context
This project supports generating and publishing small, mostly static websites. We need:
1. Reliable AI-driven UI generation with guardrails.
2. A safe serving model for websites.
3. Fast, low-cost delivery with minimal operational overhead.

We explicitly want small, mostly static websites, not arbitrary app hosting.

## Decision
1. Adopt `json-render` as the generation/render contract for builder UX.
2. Keep generation/build/publish in backend orchestration (not in-browser model execution).
3. Serve published sites as immutable static artifacts on Bunny.net (Storage Zone + CDN Pull Zone), reusing Den as the file interface.
4. Enforce a static-first output policy with a small-JS budget profile.

## Rationale
### Why json-render
1. Catalog-constrained generation reduces invalid or unsafe UI output.
2. Streaming JSON specs support responsive editing UX.
3. Export flow fits our backend build/publish pipeline.

### Why static artifact serving
1. Better reliability and lower latency for small static sites.
2. Lower cost than per-site runtime containers.
3. Strong isolation and rollback via immutable versioned artifacts.
4. Simple custom-domain support at CDN edge.
5. Reuses existing Den/Bunny file infrastructure.

## Options Considered
### Option A: Run generated React runtime per site (container/server)
Rejected.
Reasons:
1. Higher ops cost and attack surface.
2. Unnecessary for static sites.
3. Slower cold-start and weaker cache characteristics.

### Option B: Serve directly from Tentackl API
Rejected.
Reasons:
1. Mixes orchestration API concerns with public web serving.
2. Harder to scale and cache effectively.
3. Increases blast radius during API incidents.

### Option C: Static artifacts on Bunny.net via Den (Chosen)
Accepted.
Reasons:
1. Best performance/cost profile for static sites.
2. Easy versioning and rollback.
3. Clean separation of concerns by layer and service role.
4. Lowest integration friction because Den already uses Bunny.net.

## Serving Architecture (Chosen)
1. Build output: `index.html`, route HTML files, hashed assets, optional tiny JS bundle.
2. Artifact storage: versioned path in Bunny Storage Zone, accessed through Den adapters.
3. Delivery: Bunny Pull Zone CDN in front of site artifacts.
4. Domain mapping: edge route + TLS cert automation.
5. Rollback: switch active release pointer and edge origin path.

## Static/Small-JS Policy
Two publish profiles:

1. `static_zero_js`
- Pure HTML/CSS plus optional inline progressive enhancement script.
- No framework runtime bundle.

2. `static_small_js`
- JS allowed for forms/interactions only.
- Budget limits (gzip):
- Total JS <= 120 KB.
- Critical path JS <= 50 KB.
- Third-party scripts denied by default; explicit allowlist required.

Publish is blocked if profile budgets fail.

## Build and Publish Flow
1. User prompt -> `json-render` spec generation.
2. Spec persisted as draft version in `sites` domain.
3. Backend sandbox builds static artifact from approved spec.
4. Policy checks run (JS budget, disallowed dependency/script checks, secret scan).
5. If checks pass, publish release to Bunny Storage Zone via Den and serve from Bunny Pull Zone.
6. Emit release events and update site release pointer.

## Security and Compliance Guardrails
1. Backend-only model keys and tool execution.
2. Ephemeral sandbox per build job with CPU/memory/time/network limits.
3. No direct host mounts or Docker socket exposure.
4. CSP and security headers on served pages.
5. Immutable artifact hashes for auditability.

## DDD/Layers Alignment
1. `domain/sites`: project/version/build/release/domain entities and invariants.
2. `application/sites`: use cases (`Create`, `Edit`, `Build`, `Publish`, `Rollback`, `AttachDomain`).
3. `infrastructure/sites`: adapters (json-render generation, sandbox build, storage, CDN, domains, policy scan).
4. `interfaces`: router calls only use cases; no direct DB/Redis in routes.

## Consequences
### Positive
1. Predictable AI output and safer generation.
2. Fast global delivery and cheaper hosting.
3. Clear rollback and release lineage.

### Tradeoffs
1. Dynamic server-side features are out of scope for V1.
2. Requires exporter/build tooling from json-render spec to static artifact.
3. Strict budgets may reject some richer designs.

## Implementation Notes
1. Add `StaticHostingPort` default adapter targeting Bunny Pull Zone and Bunny custom-domain APIs.
2. Add `PolicyScanPort` checks for JS budgets and script/dependency allowlists.
3. Add release metadata fields: `publish_profile`, `asset_manifest`, `js_budget_report`.
4. Expose builder plugins:
- `site_create_from_prompt`
- `site_edit_from_prompt`
- `site_build_preview`
- `site_publish`
- `site_rollback`
- `site_attach_domain`
5. Add `ArtifactRepositoryPort` adapter that stores site artifacts through Den (Bunny-backed) with site/release prefixes.

## Related
1. `docs/architecture/Architecture-Guardrails.md`
