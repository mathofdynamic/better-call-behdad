# Case study: Behdad audits MarkChart

**TL;DR — Behdad audited a real, production-intent web app, reported 14 issues, and the developer
fixed all 14 in a single commit literally titled *"Fix Behdad audit findings."* Independent
re-review of the patched code confirms every issue is resolved with no regressions.**

This is a first real-world field test, run honestly and reported honestly (including its limits).

---

## The target

[MarkChart](https://github.com/mathofdynamic/markchart) — a React + TypeScript flow-diagram editor
with a Cloudflare Pages/Workers backend (D1 database, HMAC sessions, Google auth, an AI generation
endpoint, flow sharing). ~a few thousand lines; real auth, real persistence, real API. Not a
toy, not a vuln-by-design benchmark.

## What we did

1. Ran a single **`/behdad`** audit at **quick depth** (`ruff` + `bandit` + `semgrep` installed).
2. Behdad produced a Full Diagnostic Report + Prioritized Action Report and **stopped** (no
   auto-edits).
3. The developer fixed the issues and committed them (`bebcbed`).
4. **Afterwards**, four adversarial reviewers re-read the *patched* source to confirm the issues
   were genuinely resolved (they read the post-fix code, so they correctly report "clean now").

## What Behdad reported

14 findings — 2 high, 9 medium, 3 low — across logic, testing, accessibility, quality, performance,
and supply-chain. The two it led with are the kind a linter never finds:

| # | Sev | Finding | CWE |
|---|-----|---------|-----|
| 1 | med | `POST /api/*/flows` returns **200 OK but silently saves nothing** when a caller-controlled `id` collides with another user's row (later GET 404s) | CWE-754 |
| 2 | med | Markdown export **mislabels normal converging branches as "loop back"** (BFS visit order, not graph structure) — silently corrupts the control-flow meaning fed to LLMs | CWE-697 |
| 3 | high | **No automated tests** over security-critical session/API-key/share-authorization code | CWE-1120 |
| 4 | high | Core actions (load flow, add node) are **keyboard-inaccessible** (`onClick` on plain `<div>`) | WCAG 2.1.1 |
| 5 | med | Missing `vite/client` types **breaks the repo's only lint gate** (`tsc`) on a clean checkout | — |
| 6 | med | Existing parser test script wired into **no npm script or CI** | — |
| 7 | med | `FlowEditor` god component duplicates **unguarded `localStorage`** writes in several places | — |
| 8–11 | med | a11y: icon buttons without labels; modals without `role=dialog`/focus-trap; unassociated form labels; toasts without `aria-live` | WCAG |
| 12–13 | low | Synchronous `localStorage` on every drag frame; whole-canvas re-render (no `React.memo`) | CWE-400 |
| 14 | low | Dead `express`/`dotenv` prod dependencies on a Cloudflare Pages app | CWE-1104 |

It reported **zero security findings** — and an independent security review confirmed that verdict
is correct (parameterized D1 queries throughout, owner-scoped authorization, constant-time HMAC
compare, no SSRF/secret-exposure on reachable paths). So: no false negatives on security, either.

## The proof it was right: the fix commit

The developer's fix commit [`bebcbed`](https://github.com/mathofdynamic/markchart/commit/bebcbed) is
titled **"Fix Behdad audit findings: correctness, a11y, security, tests"** and its body maps to the
report one-to-one:

```
Correctness:
- Return 409 instead of false 200 when a flow upsert hits an id owned by
  another account            → finding #1
- Real cycle detection in exporter.toMarkdown()            → finding #2
Testing/CI: add vitest + tests (session sign/verify, exporter regression),
  wire import-check into npm test, add GitHub Actions CI   → findings #3, #6
Accessibility: keyboard access for sidebar/palette items, modal dialog roles
  + focus trap, aria-labels, associated form labels, toast live regions → findings #4, #8–11
Quality/perf/deps: guarded flowStore (dedupe localStorage), debounced
  autosave, React.memo nodes/edges, remove unused express/dotenv → findings #7, #12–14
```
The diff confirms it: `src/vite-env.d.ts` **added** (#5), a `409` owner-guard **added** to the flows
API (#1), a real `canReach()` reachability check **replacing** the BFS heuristic in the exporter
(#2), and new test files `functions/_lib.test.ts` + `src/lib/exporter.test.ts` + `.github/workflows/ci.yml`
**added** (#3, #6).

## The numbers

| Metric | Result |
|--------|--------|
| Raw scanner findings → reported | **18 → 14** (22% filtered as noise) |
| Rejected by the critic / abstained | 0 / 0 |
| Findings the developer acted on | **14 / 14** |
| Confirmed false positives (against the audited code) | **0** |
| Security false negatives (independent review) | **0** |
| Overall confidence (self-reported) | 0.81 |

## Honest limitations (so this stays credible)

- **Same-owner test.** MarkChart is owned by Behdad's author. This is a real first field test, not a
  blinded third-party trial. The strongest independent signal is the developer's own decision to fix
  all 14 — but we're not claiming an arms-length benchmark here.
- **Detection, not auto-fix.** This run was quick-depth and did not generate fix diffs
  (`auto_fixable` was false); the fixes were written by the developer (with an assistant). Behdad's
  value here was **finding and prioritizing**, not applying.
- **One run, one project.** A single case study is a data point, not a benchmark. More runs across
  unrelated repos are the next step.
- **"Re-verification" caveat.** The post-fix adversarial review was run by the tool's author. The
  git commit and its diff are the objective, checkable evidence — not our say-so.

## Reproduce it

```bash
git clone https://github.com/mathofdynamic/markchart.git
cd markchart && git checkout ae5b67b     # the pre-fix state Behdad audited
# then, in Claude Code with Behdad installed:
/behdad this
# compare the report against fix commit bebcbed
```

## Bottom line

On its first real audit, Behdad surfaced 14 genuine issues — including two subtle logic bugs no
linter would catch — with zero confirmed false positives and a correct clean-on-security verdict.
A developer found all 14 worth fixing and did. That's the outcome the tool is built for.
