---
type: overview
status: current
sources: [README.md, frigate/extras/README.md, docker-compose.yml, frigate/app.py]
updated: 2026-08-24
---

# Rasid360 — Overview

Rasid360 is a fork of [Frigate NVR](https://github.com/blakeblackshear/frigate) that adds a
**violation detection and ticketing layer** on top of Frigate's object detection.

Frigate answers *"what objects are in frame?"*. Rasid360 adds three things on top:

1. **Rules** that decide which detections constitute a violation (wrong-way driving, restricted
   zone entry, a stopped vehicle, a person who has fallen, a speeding car).
2. **Aggregation** so violations can be counted, charted, and trended.
3. **Tickets** so a human can work each violation through to resolution.

## The one-paragraph architecture

Frigate detects objects and publishes them to MQTT. A separate process — the
[Extras Service](components/extras-service.md) — consumes that stream and evaluates
declarative rules written in a small YAML [DSL](concepts/dsl-rule-language.md). When a rule
fires, it creates a synthetic event back in Frigate (so the violation gets a snapshot and a
recording like any other event) and writes an observation row into a **separate**
`analytics.db`. A background scheduler rolls those rows into pre-aggregated tables that a new
[dashboard API](components/api-dashboard.md) serves to a React dashboard. The same observation
row carries ticket state — `new → in_progress → solved | closed | fake`.

Full step-by-step trace: [Violation Lifecycle](concepts/violation-lifecycle.md).

## What was actually changed

Fork point is upstream commit `de066d00` ("Fix i18n #20857", 2025-11-11). On top of that:

- **24 commits**, **666 files**, **+15,814 / −3,508**

But that file count is misleading. The change breaks down as:

| Category | Scale | Notes |
|---|---|---|
| New backend subsystems | ~6,000 lines | `frigate/extras/`, `analytics_db.py`, `analytics_scheduler.py`, `api/dashboard.py` |
| New frontend | ~1,000 lines | `pages/Dashboard.tsx`, `use-dashboard-data.ts`, ticket + evidence tabs |
| Documentation | ~2,200 lines | `frigate/extras/*.md` |
| **Cosmetic rename** | **~500 files** | `FrigateConfig` → `Rasid360Config` and friends |
| Core pipeline edits | **~30 lines** | 4 files only |

Two numbers matter most. The **~30 lines** of core edits is why merging upstream is still
feasible — the violation system is almost entirely additive
([Core Pipeline Patches](components/core-pipeline-patches.md)). The **~500 files** of rename
churn is the main thing working against that, because it lands in `web/src` where upstream
changes most ([Fork Relationship](concepts/fork-relationship.md)).

## Design decisions worth knowing

**Rules are data, not code.** Adding a violation type is a YAML edit. This is the strongest
structural decision in the fork — see [DSL Rule Language](concepts/dsl-rule-language.md).

**The violation engine runs out-of-process**, coupled only through MQTT and HTTP. It cannot
stall the frame pipeline, and it can be restarted independently. The cost is that nothing
supervises it — see [Extras Service](components/extras-service.md).

**Analytics live in their own database.** `analytics.db` sits beside `frigate.db` and is never
joined to it at query time; the scheduler copies aggregates across. Dashboard reads are cheap
table scans over small pre-aggregated tables rather than scans over the events table —
[Analytics Database](components/analytics-database.md).

## Entry points for reading the code

| If you want to understand... | Start at |
|---|---|
| How a violation is decided | `frigate/extras/dsl/evaluator.py` |
| How rules are written | `frigate/extras/config.yml` |
| How a violation becomes an event | `frigate/extras/actions/dsl_violation_detector.py:136` (`_handle_violation`) |
| How charts get their numbers | `frigate/analytics_scheduler.py` |
| What the operator sees | `web/src/pages/Dashboard.tsx` |

## Current state

The system works end to end, but it carries meaningful debt: no tests over ~6,000 lines of new
backend, an unsupervised worker process, development hacks committed to `main`, and a
confirmed bug that disables two dashboard endpoints outright. All catalogued in
[Known Issues](health/known-issues.md) — read that page before trusting any dashboard number.
