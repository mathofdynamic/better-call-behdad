# Benchmarking Behdad

Two complementary measurements, both cheap to run and designed to be **reported honestly** —
including the bad runs. A tool whose evidence is only its best runs has no evidence.

## 1. Seeded self-eval (automated scoring)

`/behdad eval` (Claude Code) runs the full pipeline — scanners, inspectors, critic, manager —
against `tests/fixtures/seeded-repo/`, whose [ground truth](../tests/fixtures/seeded-repo/ground-truth.json)
is exhaustive: 5 scanner-detectable security bugs, 3 **judgment-only logic bugs** no static tool
catches, and 4 noise traps (correct code that baits false positives). Scoring is automatic via
`scripts/score_run.py` — no human triage. Key numbers:

- **recall** — planted bugs found / 8
- **judgment_recall** — the LLM layer's own number: logic bugs found / 3
- **precision** — since the manifest is exhaustive, every unmatched finding is a real FP
- **trap_hits** — any hit is a hard failure (the critic passed known-benign bait)
- **critic_kill_rate** — how much candidate volume the critic rejected

## 2. Blind trials on real repos (human-triaged)

The seeded repo can be memorized; real repos can't. Protocol:

1. Pick a repo **you know well but Behdad's author didn't write**, with at least one issue you
   already know is real. Don't tell Behdad what it is.
2. Fresh session, `/behdad <repo> --depth thorough`. Do **not** approve any fixes.
3. Triage every reported finding yourself: true positive / false positive / can't tell.
   `tests/eval/measure.py triage` generates the sheet; `measure.py score` computes precision.
4. Record whether your known issue was found (a recall spot-check — full recall on a real repo
   is unknowable, say so rather than invent a number).

**Honesty rules:** report every trial, including bad ones. No rerun-until-green — the first run
is the run (reruns may be reported as additional labeled rows). Record host, exact model ID,
date, and depth. Findings you merely disagree with are "can't tell", not FPs.

## Results

| date | host / model | repo (lang, ~LOC) | depth | reported | TP | FP | ? | precision | seeded recall | judgment recall | trap hits | notes |
|------|--------------|-------------------|-------|----------|----|----|---|-----------|---------------|-----------------|-----------|-------|
| 2026-07-03 | Claude Code / claude-fable-5 | seeded-repo (py, ~120) | quick | 8 | 8 | 0 | 0 | 1.0 | 1.0 (8/8) | 1.0 (3/3) | 0 | first seeded self-eval; staged via stage_eval.py (markers stripped); critic_kill_rate 0.429 (merged 2 cross-aspect dups, killed 4 test-noise/import findings); scanners: semgrep+bandit+ruff (gitleaks/osv/trivy missing) |

The MarkChart field test (pre-benchmark, same-owner, 14 reported / 14 fixed / 0 confirmed FP) is
documented separately in [CASE-STUDY-markchart.md](CASE-STUDY-markchart.md); it predates this
protocol and is deliberately not listed as a blind trial.
