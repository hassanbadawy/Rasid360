---
type: overview
status: current
sources: [wiki]
updated: 2026-08-25
---

# Wiki Index

Catalog of every page. Read this first when answering a question, then drill into the 2-5
relevant pages. Conventions and workflows live in [SCHEMA.md](SCHEMA.md).

## Start here

| Page | What it covers |
|---|---|
| [Overview](overview.md) | What Rasid360 is, what changed from Frigate, where to start reading code |
| [Violation Lifecycle](concepts/violation-lifecycle.md) | **The spine.** Camera frame → detection → rule → event → evidence → ticket → chart |
| [Known Issues](health/known-issues.md) | 12 catalogued issues, severity-ordered. Read before trusting dashboard numbers |

## Concepts

Cross-cutting ideas that span components.

| Page | What it covers |
|---|---|
| [Violation Lifecycle](concepts/violation-lifecycle.md) | End-to-end trace, all 9 stages, including the `sub_label` convention |
| [DSL Rule Language](concepts/dsl-rule-language.md) | The YAML authoring surface — rule types, condition expressions, templates, tuning fields |
| [Camera Access Control](concepts/camera-access-control.md) | Per-camera permissions, where they hold, and where they are broken |
| [Fork Relationship](concepts/fork-relationship.md) | Fork point, divergence, merge strategy, branch topology |

## Components

One page per subsystem, mapped to real paths.

### Backend — violation detection

| Page | Code |
|---|---|
| [Extras Service](components/extras-service.md) | `frigate/extras/main.py`, `utils/`, `actions/` |
| [DSL Engine](components/dsl-engine.md) | `frigate/extras/dsl/` |

### Backend — analytics and API

| Page | Code |
|---|---|
| [Analytics Database](components/analytics-database.md) | `frigate/analytics_db.py` |
| [Analytics Scheduler](components/analytics-scheduler.md) | `frigate/analytics_scheduler.py` |
| [Dashboard API](components/api-dashboard.md) | `frigate/api/dashboard.py` |
| [Events & Observations API](components/api-events-observations.md) | `frigate/api/event.py`, `frigate/api/media.py` |

### Frontend

| Page | Code |
|---|---|
| [Web Dashboard](components/web-dashboard.md) | `web/src/pages/Dashboard.tsx`, `hooks/use-dashboard-data.ts`, detail dialog tabs |
| [Rules Editor](components/web-rules-editor.md) | `views/settings/RulesView.tsx`, `components/settings/RuleEditDialog.tsx` |
| [Navigation & Branding](components/web-navigation-branding.md) | `use-navigation.ts`, `rasid360Config.ts`, theme, locales |

### Upstream modifications

| Page | Code |
|---|---|
| [Core Pipeline Patches](components/core-pipeline-patches.md) | `video.py`, `camera/state.py`, `track/object_processing.py`, `app.py` — all ~30 lines |

## Operations

| Page | What it covers |
|---|---|
| [Dev Environment](operations/dev-environment.md) | `run-dev.sh`, compose services, ports, logs, manual end-to-end verification |
| [Configuration](operations/configuration.md) | The two config files, env vars, git tracking, and the MP4-fixture setup |

## Health

| Page | What it covers |
|---|---|
| [Known Issues](health/known-issues.md) | Severity-ordered catalogue with evidence and suggested work order |

## Common questions → pages

| Question | Go to |
|---|---|
| How does a violation get detected? | [Violation Lifecycle](concepts/violation-lifecycle.md) |
| How do I add a new violation type? | [Rules Editor](components/web-rules-editor.md), [DSL Rule Language](concepts/dsl-rule-language.md) |
| Why is my new rule not firing? | [DSL Engine](components/dsl-engine.md) § Validation, [Configuration](operations/configuration.md) |
| Why is a chart empty? | [Known Issues](health/known-issues.md) #1, #11 |
| Why are the violation counts too high? | [Known Issues](health/known-issues.md) #2 |
| Why is the dashboard 5 minutes behind? | [Analytics Scheduler](components/analytics-scheduler.md) |
| Why is there no evidence image? | [Violation Lifecycle](concepts/violation-lifecycle.md) § 6 |
| Can we merge upstream Frigate? | [Fork Relationship](concepts/fork-relationship.md) |
| How do I run this locally? | [Dev Environment](operations/dev-environment.md) |
| Where does ticket state actually live? | [Events & Observations API](components/api-events-observations.md) |

## Maintenance

| Page | What it covers |
|---|---|
| [SCHEMA](SCHEMA.md) | Conventions and the ingest / query / lint workflows — read before editing any page |
| [Log](log.md) | Append-only record of ingests, queries, and lint passes |

## Page count

21 files: 1 index, 1 log, 1 schema, 1 overview, 4 concepts, 10 components, 2 operations, 1 health.
