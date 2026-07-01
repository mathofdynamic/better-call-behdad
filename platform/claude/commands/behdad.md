---
description: Audit a project with Behdad — security, quality, correctness, and more; report, then fix on confirmation.
argument-hint: "[path to audit] [--depth quick|thorough]"
---

Run a **Better-call-behdad** audit.

Target: `$ARGUMENTS` (if empty, audit the current working directory).

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
