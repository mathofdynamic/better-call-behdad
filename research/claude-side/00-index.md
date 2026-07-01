# Better-call-behdad — Research Index (Claude side)

Compiled overview of the six research briefs in this folder. This is my side of the
parallel research effort; the user is running an independent Deep Research pass whose
output will live in a sibling folder. We reconcile both, then move to planning.

Date compiled: 2026-07-01

---

## The briefs

| # | File | Focus | One-line takeaway |
|---|------|-------|-------------------|
| 01 | `01-standards-and-rubrics.md` | What "good" objectively means | Every standard splits into 🤖 machine-checkable vs 🧠 LLM-judgment — this split *is* the agent design. |
| 02 | `02-existing-tooling.md` | Deterministic tools to wrap | Hybrid pattern wins: tools give high-recall ground truth (SARIF), LLM does triage/dedup/explanation. |
| 03 | `03-prior-art.md` | Who built this already | Across all measured tools, **noise — not missed bugs — is the dominant failure mode** (92% below 60% signal). |
| 04 | `04-orchestration-patterns.md` | How to coordinate agents | Supervisor + map-reduce fan-out/fan-in is the right backbone; typed evidence-grounded findings + agreement-weighted aggregation. |
| 05 | `05-claude-code-skill-implementation.md` | How to build it in Claude Code / Codex | Author to the open **Agent Skills** + **AGENTS.md** standards; express orchestration per-tool. |
| 06 | `06-reporting-and-false-positives.md` | Report + confirm-before-fix + hallucination | Blend CVSS+EPSS+reachability; gate fixes at execution layer; layered FP-reduction stack. |

---

## The single most important cross-cutting finding

**The enemy is noise, not blindness.** Independently confirmed by briefs 03 and 06:
- 92% of AI review agents run below a 60% signal ratio; Copilot ~20% (03).
- ~28% of CodeRabbit comments are nitpick/noise, 13% on hallucinated assumptions (03).
- SOTA academic vuln-detector IRIS still has ~85% false-discovery rate (03).
- Best-in-class *tuned* systems: CodeRabbit ~2 FP/run, Greptile ~82% recall / ~11 FP (06).

Implication for Behdad: **precision and trust beat recall.** A confirm-before-fix tool
that cries wolf gets ignored. Every design lever below serves noise reduction.

---

## Convergent design principles (agreed across ≥2 briefs)

1. **Two-phase: deterministic-first, LLM-adjudicate.** Run real scanners (Semgrep, CodeQL,
   Bandit, Ruff, ESLint, Gitleaks, Trivy/OSV, Checkov) to get grounded, high-recall
   findings in SARIF; then the LLM triages, dedups, explains, and routes. (01, 02, 03, 06)

2. **Findings must prove themselves.** A separate judge/verifier gate with executable checks,
   repro tests, or path-reachability — plus an explicit **abstain/"don't know"** option.
   (03, 04, 06)

3. **Typed, evidence-grounded findings.** Canonical IDs (CWE/OWASP), severity, file:line,
   confidence, evidence. This is the interface between inspectors and the manager, and the
   substrate for dedup + agreement-weighted ranking. (01, 04, 06)

4. **Supervisor + map-reduce topology.** Independent read-only concerns parallelize well
   (Anthropic explicitly warns multi-agent is a *weak* fit for collaborative code-*writing*,
   but a good fit for breadth-first read-only audit). (04)

5. **Prioritize by blended risk, not raw severity.** CVSS (severity) + EPSS (exploit
   likelihood) + reachability, not CVSS alone. (06)

6. **Gate fixes at the execution layer, human-in-the-loop.** dry-run → staged → apply →
   verify → rollback; approve before side effects; don't let the model self-authorize. (06)

7. **Build to open standards for portability.** Agent Skills + AGENTS.md are the portable
   core across Claude Code / Codex / Cursor; orchestration is expressed per-tool. (05)

---

## Candidate inspector "aspects" (from 01, mapped to tools from 02)

Each aspect pairs a deterministic tool (ground truth) with LLM judgment (the hard part):

| Aspect | 🤖 Machine-checkable via | 🧠 Needs LLM judgment for |
|--------|--------------------------|----------------------------|
| Security | Semgrep/CodeQL/Bandit, Gitleaks (secrets) | Broken access control, insecure design |
| Dependencies / supply chain | OSV-Scanner, Trivy, Snyk, SBOM | License compatibility, transitive risk |
| Code quality / maintainability | Ruff, ESLint, complexity/MI metrics | SOLID adherence, code-smell severity |
| Logic / correctness | (weak tool coverage) | The core LLM value-add: does it *do the right thing* |
| Testing | coverage %, mutation score | Test meaningfulness |
| Architecture / stack fit | — | Wrong-stack, structural problems |
| Accessibility (if UI) | contrast, alt-text presence | Alt-text *quality*, semantics |

Note: **Logic/correctness has the weakest deterministic backstop** → highest hallucination
risk → needs the strongest verification gate. This is where Behdad earns its keep and where
it's most dangerous.

---

## Three candidate orchestration architectures (from 04)

1. **Supervisor + critic** — manager fans out to inspectors, a critic pass challenges
   findings before the manager synthesizes. Richest, highest token cost.
2. **Lean manager-as-tools** — inspectors exposed as tools to one manager. Simpler, cheaper.
3. **Voting ensemble** — multiple inspectors per aspect, agreement-weighted. Best FP control,
   most expensive (~4–15× token multiplier).

Cost lever: gate many-agent depth by task value, model tiering (cheap inspectors, high-
reasoning manager), and convergence halting.

---

## Implementation substrate (from 05)

- **Skill**: `SKILL.md` directory, progressive disclosure, dynamic `` !`cmd` `` injection,
  `context: fork`.
- **Subagents**: `.claude/agents/*.md` with per-agent `model` / `effort` / `tools` /
  `permissionMode`. Manager can run high `effort`; inspectors cheaper. Nested depth limit 5.
- **No enforced structured return in Claude** → specify output shape in the prompt. Codex
  offers `output_schema` / `report_agent_job_result` if we want harder guarantees there.
- **Hooks** (exit-code-2 blocking) can enforce the confirm-before-fix gate deterministically.

---

## Open questions to resolve in planning

1. **Scope of v1**: audit-and-report only, or audit-and-fix? (Fixing raises the stakes on FP.)
2. **Which aspects ship in v1** vs later? (Security + quality + logic likely core.)
3. **Tool dependency policy**: require the scanners installed, auto-install, or degrade
   gracefully to LLM-only (with a loud caveat about lost recall)?
4. **Language coverage** for v1 — the tool stack is strongest for Python/JS/TS.
5. **Which orchestration architecture** — start lean (#2) and add critic/voting for
   high-value runs, or go straight to supervisor+critic?
6. **Cross-agent**: ship Claude-only first, or the portable Agent Skills core from day one?
7. **Where do the scanners run** — bundled invocation vs assume-present on user machine?

These are the decisions I'd want your Deep Research to weigh in on before we lock the plan.
