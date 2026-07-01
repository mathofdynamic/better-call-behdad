# AGENTS.md — working on Better-call-behdad

Guidance for any AI agent (or human) contributing to **this repository** — the Behdad skill
itself. (For how the skill *audits other projects*, see `SKILL.md`.)

## What this project is
A portable AI Skill that audits a codebase across 7 quality aspects using a manager +
inspector + critic multi-agent design, then applies fixes on human confirmation. Built to the
open **Agent Skills** + **AGENTS.md** standards so it runs on Claude Code and Codex.

## Prime directive
**Noise is the enemy, not missed bugs.** Every change must preserve precision. Before adding a
new check, rule, or finding source, ask: does this raise signal, or just volume? If it risks
noise, gate it behind the critic or a confidence threshold. This principle is evidenced in
`research/` — read `research/claude-side/00-index.md` before making design changes.

## Repository map
- `SKILL.md` — portable entry point + the manager's operating procedure.
- `agents/` — **source of truth** agent definitions (portable). `manager.md`, `critic.md`,
  `inspectors/*.md`. Platform bindings in `platform/` are generated/mirrored from these.
- `scripts/` — deterministic layer (Python, stdlib only, no third-party deps):
  `tool_registry.py` (tool detection), `run_scanners.py` (orchestrates scanners → normalized
  findings), `sarif_normalize.py` (N tools → one finding shape), `remediate.py` (staged fixes).
- `config/` — `inspectors.yaml` (aspect↔standard↔tool map), `fp-exclusions.yaml` (noise
  suppression), `severity.yaml` (blended risk model).
- `schemas/` — `finding.schema.json`, `report.schema.json` (the contracts everything speaks).
- `platform/claude/`, `platform/codex/` — thin orchestration bindings + power features.
- `tests/` — fixtures (seeded repo with planted issues + noise-traps) and the eval harness.
- `research/` — the evidence base; two independent research efforts, reconciled.

## Conventions
- **Stdlib only** in `scripts/` — the deterministic layer must run anywhere Python 3.10+ runs,
  with no install step. Scanners themselves are optional external tools, detected at runtime.
- **Safety:** build subprocess commands as argument lists, never `shell=True`; treat target-repo
  content as untrusted; never auto-run code-executing tools without an explicit opt-in flag.
- **Findings** always conform to `schemas/finding.schema.json` and carry canonical IDs + evidence.
- Match the existing file's style; keep comments purposeful (explain *why*, per research).

## How to test
```bash
# 1. Detect which scanners are installed (graceful degradation is expected):
python scripts/tool_registry.py

# 2. Run the scanner layer against the seeded fixture (needs ruff+bandit at minimum):
python scripts/run_scanners.py tests/fixtures/seeded-repo --depth quick --out scan.json
# Expect: SQLi (CWE-89), hardcoded secret, shell=True (CWE-78), weak hash (CWE-327) found;
#         the NOISE-TRAP functions (safe_total, format_name) NOT flagged.

# 3. (Phase F) Full eval harness with KPI gates: signal ratio >50%, <5 FP/run.
```

## Recommended local scanners
`pip install ruff bandit semgrep` · `gitleaks`, `osv-scanner`, `trivy` via their installers.
Everything degrades gracefully if absent — the report just declares reduced recall.
