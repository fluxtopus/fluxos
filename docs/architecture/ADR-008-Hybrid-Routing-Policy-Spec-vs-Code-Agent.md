# ADR-008: Hybrid Routing Policy — Spec Mode vs Code-Agent Mode

## Status
Proposed

## Date
2026-02-13

## Context
ADR-007 establishes the static-artifact serving model and json-render generation contract.
We need a decision framework for **when** the system should use lightweight spec-based generation versus spinning up a full Claude Code agent session. The wrong default wastes cost/latency (over-using code-agent) or limits capability (over-using spec mode).

## Decision
Route every edit request through a **classifier** that picks one of three execution tiers.
The classifier runs before any sandbox or LLM call, keeping the decision cheap and auditable.

## Execution Tiers

### Tier 1 — Spec Mode (default)
**What:** LLM generates or patches a json-render spec. A deterministic builder converts the spec to static HTML/CSS. No ephemeral container needed for generation; build sandbox is optional for asset optimization.

**When to use:**
- New site creation from a site description.
- Text/content changes (copy, headings, descriptions).
- Section reordering, adding, or removing.
- Color, font, and spacing changes.
- Image swaps (URL replacement).
- Adding standard components from the catalog (hero, testimonials, comparison table, FAQ, footer, contact form).

**Characteristics:**
- Fast (single LLM call + deterministic render).
- Cheap (no container, no package installs).
- Highly reproducible (same spec = same output).
- Easy to policy-scan (spec is structured data).

### Tier 2 — Patch Mode (intermediate)
**What:** LLM generates file-level diffs (unified diff format or structured patches). A deterministic backend applies the patches to the current file snapshot. Build sandbox runs if compilation is needed.

**When to use:**
- Small CSS/JS tweaks that go beyond spec vocabulary.
- Adding inline scripts (form validation, scroll behavior, analytics snippet).
- Modifying generated HTML structure in ways the spec doesn't express.
- Fixing bugs or rendering issues in existing output.

**Characteristics:**
- Moderate cost (LLM call + optional build container).
- Reproducible (diff is auditable and reversible).
- Agent does NOT run arbitrary commands; patches are applied server-side.
- Policy scan runs on resulting files before preview.

### Tier 3 — Code-Agent Mode (opt-in / escalation)
**What:** Ephemeral container with Claude Code CLI, loaded with site files from Den. Agent has filesystem and restricted shell access. Full edit session with iterative builds and previews.

**When to use:**
- Multi-file structural changes (e.g., "convert to a multi-page site with shared nav").
- Adding client-side libraries that require `npm install` + build step.
- Custom animations, interactive widgets, or canvas/WebGL elements.
- Complex layout restructuring that exceeds spec/patch expressiveness.
- User explicitly requests "advanced edit" or code-level control.

**Characteristics:**
- Highest cost and latency (container lifecycle, package installs, iterative LLM calls).
- Least reproducible (agent may take different paths).
- Strongest capability (can do anything within sandbox constraints).
- Strictest security gates required before publish.

## Routing Classifier

### Input Signals
1. **User prompt** — natural language intent.
2. **Current site complexity** — number of files, presence of JS, build config.
3. **Edit scope** — single section vs. structural change.
4. **User preference** — spec-first (Tier 1) vs. code-agent (Tier 3).
5. **Explicit escalation** — user clicks "Advanced Edit" or uses a power keyword.

### Classification Logic (V1 — Rule-Based)
```
IF user explicitly requests code-agent OR "advanced edit":
    → Tier 3

IF edit involves npm/package install, multi-file structural change, or custom JS logic:
    → Tier 3

IF edit involves CSS/JS tweaks beyond spec vocabulary OR bug fixes:
    → Tier 2

ELSE:
    → Tier 1
```

### Classification Logic (V2 — LLM-Assisted)
A lightweight LLM call (Haiku-class) classifies the prompt before execution:
```json
{
  "prompt": "Add a smooth scroll animation to the hero section",
  "current_site": { "files": 3, "has_js": false, "has_build": false },
  "classification": {
    "tier": 2,
    "reason": "Requires inline JS addition, within patch vocabulary",
    "estimated_complexity": "low"
  }
}
```
Cost of classification call is negligible compared to execution.

### Escalation and Fallback
- If Tier 1 generation fails validation or produces poor output → auto-retry once → escalate to Tier 2.
- If Tier 2 patch fails to apply cleanly → escalate to Tier 3.
- If Tier 3 exceeds timeout or budget → fail with user notification, no silent retry.
- User can always manually override tier selection in the UI.

## Ephemeral Session Lifecycle (Tier 3)

```
1. Lock:      Acquire single-writer lock for site project.
2. Snapshot:   Download current release files from Den to workspace.
3. Provision:  Start ephemeral container from warm pool (or cold-start).
4. Inject:     Copy workspace files + prompt into container.
5. Execute:    Claude Code runs with restricted tools and spending cap.
6. Extract:    Copy output files from container.
7. Teardown:   Destroy container immediately.
8. Build:      Run build pipeline (if needed) in a separate sandbox.
9. Scan:       Policy gates (JS budget, secrets, CSP, allowlists).
10. Preview:   Generate signed preview URL from scanned artifact.
11. Approval:  User reviews preview.
12. Publish:   Upload as new Den version → atomic release pointer swap.
13. Unlock:    Release single-writer lock.
```

Failure at any step before Publish leaves the active release untouched.

## Sandbox Constraints (All Tiers)

| Constraint | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|
| Container | None | Optional (build only) | Required |
| Network | None | Registry allowlist | Registry allowlist |
| Shell access | None | None | Restricted (no curl, no wget, allowlisted commands only) |
| Max duration | 30s | 60s | 300s |
| Max LLM cost | $0.05 | $0.10 | $0.50 |
| Max output size | 2 MB | 5 MB | 20 MB |
| JS budget | Per publish profile | Per publish profile | Per publish profile |

## Security Considerations
1. Tier 1 and Tier 2 never execute user-influenced code server-side. Output is data (spec or diff), applied deterministically.
2. Tier 3 runs inside an ephemeral container with no host mounts, no Docker socket, restricted network, and hard resource limits.
3. All tiers pass through the same policy scan before publish. Tier routing does not bypass security gates.
4. Claude Code API key used in Tier 3 is scoped with spending limits and has no access to internal services.
5. Audit trail records: tier used, prompt, input file hash, output file hash, policy scan result, approval status.

## Consequences

### Positive
1. 70-80% of edits avoid container overhead entirely.
2. Security surface is minimal for the common path.
3. Users still get full agent power when they need it.
4. Predictable latency profile per tier for capacity planning.
5. Graceful escalation prevents dead ends.

### Negative
1. Three code paths to maintain and test.
2. Classification errors can pick wrong tier (mitigated by escalation + manual override).
3. Spec vocabulary limits what Tier 1 can express (mitigated by expanding catalog over time).

## Related
1. `docs/architecture/ADR-007-Json-Render-Static-Site-Serving.md`
2. `docs/architecture/Architecture-Guardrails.md`
