# Architecture Guardrails

## Purpose
Prevent architectural drift by enforcing clean layering, consistent dependency rules, and clear ownership boundaries.

## Layering Rules
1. `interfaces` can depend on `application` and `domain` only.
2. `application` can depend on `domain` and `infrastructure` only.
3. `domain` cannot depend on any other layer.
4. `infrastructure` cannot depend on `interfaces`.

## Forbidden Patterns
1. Router or inbox tool calling SQLAlchemy/Redis directly.
2. Domain models importing anything from `infra` or `interfaces`.
3. Event publishing outside EventBus port.
4. Multiple sources of truth for the same entity.

## Deprecated / Legacy Patterns
1. YAML workflow specs/templates are legacy; do not add or extend them.
2. Workflow scheduler helpers or workflow-only routes are legacy; do not use for new flows.
3. Prefer Tasks + Flux (InboxAgent) for durable execution and orchestration.

## Required Patterns
1. Every user-facing flow must have an application use case.
2. All external dependencies are accessed through ports.
3. Repositories own data mapping between domain and persistence models.

## Review Checklist
1. Does this change introduce a cross-layer import violation?
2. Does it bypass a use case and call storage directly?
3. Does it add a new event schema without versioning?
4. Does it add or change a public contract without tests?
5. Is the source of truth preserved for this entity?

## CI Enforcement Suggestions
1. Static import rules for package boundaries.
2. Lint rule: disallow `src/database` imports in `src/services` or `src/api`.
3. Contract tests for endpoints and event payloads.
