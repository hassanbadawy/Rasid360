# Wiki Schema

The maintenance contract for `wiki/`. Read this before editing any page in it.

Pattern source: [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
by Andrej Karpathy. This wiki is an instantiation of that pattern with the **codebase as the
raw source layer**.

## The three layers

| Layer | What it is | Who owns it |
|---|---|---|
| **Raw sources** | The repo itself — Python, TypeScript, YAML, git history. Immutable from the wiki's point of view. | Humans (via normal development) |
| **The wiki** | `wiki/**/*.md`. Summaries, component pages, concept pages, traces. | The LLM, entirely |
| **The schema** | This file. Conventions + workflows. | Human and LLM, co-evolved |

The critical inversion versus normal docs: **you do not hand-write wiki pages.** You change
code; the LLM re-reads and re-files. If a page is wrong, fix the ingest workflow, not just
the page.

## Directory layout

```
wiki/
├── SCHEMA.md          # this file
├── index.md           # content catalog — every page, one line each
├── log.md             # append-only chronological record
├── overview.md        # what Rasid360 is, in one page
├── concepts/          # cross-cutting ideas that span components
├── components/        # one page per subsystem, mapped to real paths
├── operations/        # how to run, configure, deploy
└── health/            # known issues, contradictions, gaps
```

## Page conventions

**Every page opens with a frontmatter block:**

```yaml
---
type: concept | component | operations | health | overview
status: current | stale | draft
sources: [frigate/api/dashboard.py, web/src/pages/Dashboard.tsx]
updated: 2026-08-24
---
```

`sources` is the load-bearing field. It lists the files the page was derived from. When any
of those files change, the page is a **re-ingest candidate**. Grep it:

```bash
grep -l "frigate/api/dashboard.py" wiki/**/*.md
```

**Links are relative markdown**, not `[[wikilinks]]` — so they resolve in VSCode, on GitHub,
and in Obsidian alike: `[DSL Rule Language](concepts/dsl-rule-language.md)`.

**Code references cite file and line**: `frigate/api/dashboard.py:666`. Line numbers drift;
that is what `status: stale` and the lint pass are for. Prefer citing a symbol name plus the
file when the exact line is incidental.

**Claims are anchored.** Every non-obvious assertion names the file that proves it. A page
that asserts behaviour with no `sources` entry backing it is a lint finding.

**Verified vs. inferred.** Mark inference explicitly with *(inferred)* when the code does not
directly prove the claim. Do not let a plausible reading harden into a stated fact.

## Workflows

### Ingest

Triggered by: a merged branch, a new subsystem, a dependency change, or an upstream merge.

1. Read the diff (`git diff <base>..HEAD -- <paths>`), not just the final files — intent lives
   in the change.
2. Identify which existing pages the change touches (grep `sources:`).
3. Update those pages. **Update, do not append** — rewrite the affected section so the page
   reads as a coherent whole, not a changelog.
4. Create new pages for genuinely new subsystems.
5. Update `index.md`.
6. Append one entry to `log.md`.
7. If the change contradicts an existing claim, resolve it — do not leave both. If it cannot
   be resolved from the code, file it in `health/known-issues.md`.

A single meaningful change should touch 3-10 pages. If it touches one, the cross-references
are probably too thin.

### Query

Asking a question against the wiki:

1. Read `index.md` first. It exists so you can find pages without grepping the whole tree.
2. Drill into the 2-5 relevant pages.
3. **Verify against the code before answering.** The wiki is a map; the repo is the terrain.
   For anything load-bearing — a security claim, a bug, an API contract — re-read the source.
4. Answer with citations to both wiki pages and source files.
5. **File good answers back.** A trace, comparison, or diagnosis that took real work becomes a
   new page. Explorations should compound, not evaporate into chat history.

### Lint

Run periodically, or before a release / upstream merge:

- **Staleness** — for each page, has any file in its `sources` changed since `updated`?
- **Contradictions** — do two pages claim different things about the same behaviour?
- **Orphans** — pages with no inbound links from any other page.
- **Gaps** — concepts referenced repeatedly across pages but with no page of their own.
- **Resolved issues** — does `health/known-issues.md` still list things that are now fixed?
- **Dead citations** — do the cited files and symbols still exist?

Staleness sweep:

```bash
for f in $(find wiki -name '*.md'); do
  upd=$(grep -m1 '^updated:' "$f" | cut -d' ' -f2)
  for src in $(sed -n 's/^sources: \[\(.*\)\]/\1/p' "$f" | tr -d ',' ); do
    [ -e "$src" ] || echo "DEAD SOURCE: $f -> $src"
  done
done
```

## Log format

Append-only, newest at the bottom. Consistent prefix so it stays greppable:

```
## [YYYY-MM-DD] <ingest|query|lint|fix> | <short title>
```

```bash
grep "^## \[" wiki/log.md | tail -5
```

## Scope boundary

This wiki documents **Rasid360's own additions and modifications**. It does not re-document
upstream Frigate — that is what [docs.frigate.video](https://docs.frigate.video) is for. When
upstream behaviour matters, link out and state only the delta.

The one exception is [Fork Relationship](concepts/fork-relationship.md), which exists
precisely to track the seam between the two.
