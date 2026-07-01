<!-- Add your generated banner at assets/banner.png and it will render here -->
<p align="center">
  <img src="assets/banner.png" alt="Better-call-behdad" width="100%">
</p>

# Better-call-behdad

> _"Better call Behdad."_ — a project-manager-in-a-box for your codebase.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
&nbsp;Runs on **Claude Code** and **OpenAI Codex**.

Named after Behdad, a great friend and a great project manager, **Better-call-behdad** is a
portable AI **Skill** that audits an existing project the way a seasoned tech lead would: it
checks security, code quality, correctness, performance, testing, dependencies, and
accessibility; explains what's wrong in plain language; tells you what to do about it, in
priority order; and — only after you say yes — fixes it, verifies the fix, and rolls back if
anything breaks.

It exists because AI-assisted ("vibe-coded") projects often silently violate best practices,
and **developers don't always know what they don't know.** Behdad is the missing quality-control
pass.

## The idea in one picture

```
/behdad → understand → scan (real tools) → 7 inspectors → critic gate → manager report
                                                                              │
                              you approve ─────────────────────────────┐     ▼
                                                                        └► fix · verify · rollback
```

A **manager** agent (high reasoning) coordinates seven specialized **inspector** agents, a
**critic** agent makes every finding prove itself, and nothing touches your code without your
explicit confirmation.

## Design axiom

**Noise is the enemy, not missed bugs.** Research (see [`research/`](research/)) shows most AI
review tools drown users in false positives — 92% run below a 60% signal ratio. Behdad
deliberately trades recall for **precision and trust**: it grounds findings in real
static-analysis tools, suppresses known-noisy categories, verifies adversarially, and abstains
when unsure.

## Status

**All six build phases are complete and the deterministic layers are green (18/18 eval checks).**
The scanner layer, aggregation engine, execution-layer fix gate, staged remediation with rollback,
suppression store, and Claude + Codex agent bindings are all in place and tested headlessly. The
LLM orchestration (manager + inspectors + critic) is authored and ready to run in a live agent
session. See [`AGENTS.md`](AGENTS.md) for the build map and [`tests/eval/run_eval.py`](tests/eval)
for the KPI harness.

```bash
python tests/eval/run_eval.py     # runs the deterministic scorecard
```

## Portability

Built to the open **Agent Skills** and **AGENTS.md** standards, so the same audit runs on Claude
Code and OpenAI Codex, with Claude-specific power features (hooks-based fix gating) as optional
add-ons.

## Install

Full steps for Claude Code and Codex are in [`INSTALL.md`](INSTALL.md). The short version:

```bash
git clone https://github.com/mathofdynamic/better-call-behdad.git
cd better-call-behdad
python platform/claude/install.py          # Claude Code (user-level)
# optional, for full recall:
pip install ruff bandit semgrep            # + gitleaks, osv-scanner, trivy
```

Then, in a new Claude Code session:

```
/behdad path/to/your/project
```

or just ask: *"audit this project with behdad."* Verify anytime with
`python tests/eval/run_eval.py`.

## License

MIT
