---
description: Audit a project with Behdad — security, quality, correctness, and more; report, then fix on confirmation.
argument-hint: "[this | path/to/project | eval] [--since last-run] [--depth quick|thorough]"
---

Run a **Better-call-behdad** audit.

**Resolve the target** from `$ARGUMENTS`:
- If it is empty, or the word **`this`**, **`here`**, **`.`**, **`cwd`**, or **`current`** →
  audit the **current working directory** (run `pwd` to get its absolute path).
- If it is the word **`eval`** → run the **self-evaluation** against the skill's seeded repo
  (see "Eval mode" at the bottom) instead of a normal audit.
- Otherwise treat the (first) argument as the path to the project to audit.
- Any `--depth quick|thorough` may appear alongside; default to `quick`.
- **Incremental:** if `--since last-run` (or `--since <git-ref>`) is present, pass it through to the
  scanner so Behdad only re-checks files changed since its last run (or that ref) and reports a
  New / Fixed / Still-open delta. Without it, a full audit runs. Behdad remembers each run in
  `<target>/.behdad/last-run.json`, and always saves the report to `<target>/.behdad/report-latest.md`.

Confirm the resolved absolute target path back to the user in one line before you start
(e.g. "Auditing: C:\\Users\\...\\my-project") so there's no ambiguity about what's being scanned.

Follow the skill's operating procedure exactly:

1. Establish `BEHDAD_HOME` — the absolute path of the installed skill directory (where its
   `SKILL.md`, `scripts/`, `agents/`, `config/` live; e.g. `~/.claude/skills/better-call-behdad`).
   This is NOT the project you're auditing. Read `$BEHDAD_HOME/SKILL.md` and
   `$BEHDAD_HOME/agents/manager.md` — you are acting as the **manager**.
2. Set the environment for this run so the safety gate is armed: `BEHDAD_ACTIVE=1` (the
   `PreToolUse` hook will hard-block any edit until the user approves the action report).
3. Execute steps 0–7 from `agents/manager.md`:
   scope → deterministic scan (`scripts/run_scanners.py`) → fan out the applicable inspector
   subagents in parallel → critic gate → `scripts/aggregate.py` → present the Full Diagnostic +
   Prioritized Action reports → **STOP and ask for confirmation** → remediate only what's approved
   (`scripts/remediate.py`, with rollback) → record dismissals (`scripts/suppressions.py`).

Precision over recall throughout: ground findings in evidence, surface coverage gaps and missing
tools honestly, and ABSTAIN rather than guess. Do not modify a single file before the user says yes.

## Eval mode (`/behdad eval`)

Scores the full pipeline — scanners AND the LLM layer (inspectors, critic, you) — against the
skill's seeded repo, whose ground truth is exhaustive. Do NOT audit the fixture in place:

1. Establish `BEHDAD_HOME` as above; set `BEHDAD_ACTIVE=1`.
2. Stage the fixture into scratch space — NEVER audit it in place and never plain-copy it:
   `python $BEHDAD_HOME/scripts/stage_eval.py $BEHDAD_HOME/tests/fixtures/seeded-repo <scratch>/eval-target`
   Staging blanks the EXPECT-*/NOISE-TRAP marker comments (which would leak the answers to the
   inspectors) while preserving line numbers, and excludes ground-truth.json.
3. Run the normal procedure at `--depth quick` through aggregation (steps 0–4): scan →
   inspectors → critic → `scripts/aggregate.py --out <scratch>/report.json`. **Stop before the
   fix phase** — eval never remediates. Do not read `ground-truth.json` yourself and never pass
   it to the inspectors or critic: knowing the answers invalidates the eval.
4. Score it:
   `python $BEHDAD_HOME/scripts/score_run.py <scratch>/report.json --truth $BEHDAD_HOME/tests/fixtures/seeded-repo/ground-truth.json`
5. Show the user the scorecard verbatim: recall, **judgment_recall** (did the logic inspector
   find the planted off-by-one / inverted condition / silent failure?), precision, trap_hits
   (any hit is a hard failure — the critic passed known-benign bait), and critic_kill_rate.
   Report misses and false positives honestly; a bad score is a finding, not an embarrassment.
6. Offer to append the run as a row to `docs/BENCHMARK.md` (host, model, date, numbers).
