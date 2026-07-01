"""Generate the Codex subagent binding files (TOML) for Behdad's inspectors + critic.

Mirror of the Claude generator, targeting OpenAI Codex. Same portability discipline: the real
instructions stay in `agents/` (single source of truth); this only expresses Codex-specific
orchestration (reasoning effort, sandbox, structured output schema).

NOTE ON THE CODEX SCHEMA: Codex's agent-definition format is evolving. The fields written here
(name/description/model/model_reasoning_effort/sandbox_mode/output_schema/instructions) reflect the
documented shape at time of writing; adjust to your installed Codex version if it differs. The
`instructions` deliberately point Codex to read the portable files rather than duplicating them.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent

INSPECTORS = ["security", "quality", "logic", "performance", "testing", "supply-chain", "accessibility"]

# Codex can enforce a structured return; point it at the finding schema.
SCHEMA_REL = "schemas/finding.schema.json"

TEMPLATE = '''# Behdad {title} {kind} — Codex agent binding (generated; edit agents/ not here)
name = "behdad-{name}"
description = "{desc}"
model = "{model}"
model_reasoning_effort = "{effort}"
# Read-only inspection: no writes to the target during audit (the manager gates fixes separately).
sandbox_mode = "read-only"
# Codex will validate the agent's return against this JSON Schema (array of findings).
output_schema_ref = "{schema}"

instructions = """
You are Behdad's {title} {kind}. The manager gives you BEHDAD_HOME (absolute path to the skill) and
the target repo path in your task prompt. BEHDAD_HOME holds your instructions/config; the target
repo is what you audit — don't confuse them. Read these (under BEHDAD_HOME), then execute against
your slice of scan.json from the task prompt:
  1. Read $BEHDAD_HOME/{instr}
  2. Read $BEHDAD_HOME/agents/_common-finding-protocol.md{extra}
Return ONLY a JSON array of findings conforming to $BEHDAD_HOME/{schema}. Precision over recall; ABSTAIN when unsure.
"""
'''

INSPECTOR_DESC = {
    "security": "Security audit: injection, secrets, weak crypto, broken access control, insecure design.",
    "quality": "Code quality & maintainability: SOLID, complexity, structural smells with real cost.",
    "logic": "Logic & correctness: off-by-one, inverted conditions, mishandled errors, contract violations.",
    "performance": "Performance: N+1 queries, super-linear complexity, unbounded resources on hot paths.",
    "testing": "Testing & robustness: untested critical paths, assertion-free tests, missing edge cases.",
    "supply-chain": "Dependencies & licenses: known-vulnerable packages, license compatibility, hygiene.",
    "accessibility": "Accessibility vs WCAG 2.2: alt text, labels, keyboard operability, ARIA.",
}


def write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


for asp in INSPECTORS:
    title = asp.replace("-", " ").title()
    write(OUT / f"behdad-{asp}.toml", TEMPLATE.format(
        name=asp, desc=INSPECTOR_DESC[asp], model="gpt-5-codex", effort="medium",
        title=title, kind="inspector", instr=f"agents/inspectors/{asp}.md",
        schema=SCHEMA_REL, extra="",
    ))

write(OUT / "behdad-critic.toml", TEMPLATE.format(
    name="critic",
    desc="Adversarially verifies candidate findings (category exclusion, reachability, repro); kills false positives.",
    model="gpt-5-codex", effort="high",
    title="Critic", kind="verifier", instr="agents/critic.md", schema=SCHEMA_REL,
    extra="\n  3. Apply config/fp-exclusions.yaml and config/severity.yaml.",
))
print("done")
