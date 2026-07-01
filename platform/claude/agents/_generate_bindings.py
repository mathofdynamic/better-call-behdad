"""Generate the thin Claude subagent binding files for Behdad's inspectors + critic.

Each binding is a Claude Code subagent: YAML frontmatter (name/description/tools/model) plus a
short body that points the subagent at its portable instructions in `agents/`. Keeping the real
instructions in `agents/` (single source of truth) and the platform specifics here is the
portability discipline from the plan. Re-run this whenever the roster or tiers change.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent

INSPECTORS = ["security", "quality", "logic", "performance", "testing", "supply-chain", "accessibility"]

TEMPLATE = """---
name: {name}
description: >-
  {desc}
tools: {tools}
model: {model}
---

You are Behdad's **{title}** {kind}. Your complete, authoritative operating instructions live in
the skill's own directory. The manager gives you **BEHDAD_HOME** (the absolute path to the skill)
and the **target repo path** in your task prompt. The target repo is what you AUDIT; BEHDAD_HOME is
where your instructions and config live — never confuse them.

Read these now (all under BEHDAD_HOME), then execute:

1. Read `$BEHDAD_HOME/{instr}` (your aspect-specific instructions).
2. Read `$BEHDAD_HOME/agents/_common-finding-protocol.md` (shared output + precision rules).{extra}

Your other input is your slice of `scan.json` (the deterministic findings for your aspect), also in
the task prompt. Follow the protocol exactly and return ONLY the JSON array of findings. Precision
over recall — ABSTAIN when unsure.
"""

INSPECTOR_DESC = {
    "security": "Audits security: injection, secrets, weak crypto, broken access control, insecure design. Spawned by the Behdad manager during an audit.",
    "quality": "Audits code quality & maintainability: SOLID, complexity, structural smells with real cost. Spawned by the Behdad manager.",
    "logic": "Audits logic & correctness: off-by-one, inverted conditions, mishandled errors, contract violations. Highest scrutiny. Spawned by the Behdad manager.",
    "performance": "Audits performance: N+1 queries, super-linear complexity, unbounded resources on hot paths. Spawned by the Behdad manager.",
    "testing": "Audits testing & robustness: untested critical paths, assertion-free tests, missing edge cases. Spawned by the Behdad manager.",
    "supply-chain": "Audits dependencies & licenses: known-vulnerable packages, license compatibility, dependency hygiene. Spawned by the Behdad manager.",
    "accessibility": "Audits accessibility against WCAG 2.2: alt text, labels, keyboard operability, ARIA. Spawned by the Behdad manager.",
}


def write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


for asp in INSPECTORS:
    title = asp.replace("-", " ").title()
    write(OUT / f"behdad-{asp}.md", TEMPLATE.format(
        name=f"behdad-{asp}",
        desc=INSPECTOR_DESC[asp],
        tools="Read, Grep, Glob, Bash",
        model="sonnet",
        title=title,
        kind="inspector",
        instr=f"agents/inspectors/{asp}.md",
        extra="",
    ))

# Critic runs high-reasoning and may run small checks to prove/refute findings.
write(OUT / "behdad-critic.md", TEMPLATE.format(
    name="behdad-critic",
    desc="Adversarially verifies candidate findings: category exclusion, reachability, repro. Kills false positives. Spawned by the Behdad manager after inspectors report.",
    tools="Read, Grep, Glob, Bash",
    model="opus",
    title="Critic",
    kind="verifier",
    instr="agents/critic.md",
    extra="\n3. Apply `config/fp-exclusions.yaml` and `config/severity.yaml`.",
))
print("done")
