# Better Call Behdad vs. Superpowers

> TL;DR — They aren't competitors. **Superpowers helps you *build* code well; Behdad checks whether code is *actually good, safe, and complete*.** The ideal workflow uses both: build with Superpowers, audit with Behdad before you ship.

[Superpowers](https://github.com/obra/superpowers) is a broad software‑development *methodology and skills framework*. Better Call Behdad is a deep, focused *audit skill*. They cover opposite halves of the development lifecycle.

## Side by side

| | **Better Call Behdad** | **Superpowers** |
|---|---|---|
| **Core question** | "Is this existing code actually good / safe / complete?" | "How do I *build* new code well?" |
| **Type** | A single deep **audit skill** + agent team | A **framework/library of 17+ skills** + methodology |
| **When you use it** | *After* code exists — review, pre‑ship, inherited or vibe‑coded projects | *Before / during* writing — from idea to merged branch |
| **Architecture** | Manager → 7 specialized inspectors → adversarial critic → gated fix‑on‑confirm | 7‑stage workflow: brainstorm → worktree → plan → subagent TDD → review → finish |
| **Design axiom** | "Noise is the enemy" — precision over recall, ABSTAIN when unsure, false‑positive exclusion | "Don't jump to code" — enforce TDD (red/green), YAGNI, DRY, structured process |
| **Output** | Diagnostic report + prioritized fixes, staged / verified / rollback | Working, tested, reviewed feature on a branch |
| **Portability** | Claude Code + Codex | Claude Code, Cursor, Copilot CLI, Kimi, OpenCode, Pi, … |

## They're complementary, not rivals

The ideal workflow is:

1. **Build** a feature with Superpowers (TDD, plans, subagent‑driven development).
2. **Audit** it with Behdad before shipping (security, correctness, quality, completeness).

You can use both on the same project. Behdad is *the auditor you run on code Superpowers — or anything else — produced.*

## Where Behdad is stronger / more differentiated

- **Focus & depth.** Behdad does one hard thing — *trustworthy* auditing — and engineers hard against the real failure mode of AI review tools: false‑positive flooding.
- **Rigor around trust.** An adversarial critic gate, deterministic scanners for ground truth, confidence calibration, and a baked‑in "how this audit performed" measurement (raw findings → reported, % filtered as noise). Most audit tools never self‑report their own noise ratio.
- **Real fix loop.** Staged `git apply` → verify → auto‑rollback behind a human confirmation gate — a genuine remediation pipeline, not just review comments.

## Where Superpowers is stronger

- **Breadth & adoption.** A whole methodology with 17+ skills, multi‑platform reach, and meaningful visibility. It spans the *entire* build lifecycle; Behdad covers one phase.
- **Maturity & reach.** More platforms, more surface area, more real‑world usage today.

## Verdict

Neither is "better" — they aim at different targets.

- **Superpowers wins on scope** (a full build methodology).
- **Behdad wins on precision within its niche** (nobody else is engineering this hard against audit false positives with a critic gate + self‑measured noise ratio).

Behdad's realistic positioning isn't "beat Superpowers" — it's **"the auditor you run on the code you just built."** That's a sharper, more defensible identity than becoming another do‑everything framework.

### Honest caveat

Behdad's LLM orchestration is authored but not yet proven live end‑to‑end across many repos — so far one same‑owner field test (see [`CASE-STUDY-markchart.md`](./CASE-STUDY-markchart.md)). The next step is blind trials on unrelated repos for a real benchmark. Superpowers has both breadth and usage today; Behdad's edge is design rigor within a narrow, valuable niche.
