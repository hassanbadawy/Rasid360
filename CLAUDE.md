# Rasid360

A fork of [Frigate NVR](https://github.com/blakeblackshear/frigate) adding violation detection
and ticketing. Fork point: upstream `de066d00` (2025-11-11).

## Read the wiki first

`wiki/` is an LLM-maintained knowledge base covering this fork's architecture. Start at
[wiki/index.md](wiki/index.md).

- **New to the repo?** [wiki/overview.md](wiki/overview.md), then
  [wiki/concepts/violation-lifecycle.md](wiki/concepts/violation-lifecycle.md)
- **Before trusting any dashboard number:** [wiki/health/known-issues.md](wiki/health/known-issues.md)
- **Before editing the wiki:** [wiki/SCHEMA.md](wiki/SCHEMA.md) — it defines the conventions and
  the ingest / query / lint workflows

## Maintaining the wiki

The wiki is generated and maintained by the LLM, not hand-written. After a substantive change:

1. Find affected pages — each page's frontmatter lists the source files it was derived from:
   ```bash
   grep -rl "path/to/changed_file.py" wiki/
   ```
2. Update those pages (rewrite the affected section; do not append a changelog).
3. Update `wiki/index.md` if pages were added or removed.
4. Append one entry to `wiki/log.md` using the format in SCHEMA.md.

Full workflows in [wiki/SCHEMA.md](wiki/SCHEMA.md).

## Scope

The wiki documents **this fork's additions only**. Upstream Frigate behaviour is documented at
[docs.frigate.video](https://docs.frigate.video).
