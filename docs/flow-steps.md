# Better-call-behdad — flow (plain step/edge list)

Tool-agnostic description of the audit flow. Nodes and edges below map directly to a MarkChart
flow (or any flow tool). Labels are plain text — no `<br/>`, no `&`, no emojis — so nothing renders
literally.

## Steps (nodes)

| ID | Type | Label |
|----|------|-------|
| S0 | start   | User runs /behdad on a project |
| S1 | process | 0 - Understand and scope |
| S2 | process | 1 - Deterministic scan with real tools |
| S3 | process | 2 - Inspect (7 specialists run in parallel) |
| S4 | process | 3 - Critic gate (verify findings, drop false positives) |
| S5 | process | 4 - Aggregate (dedup, rank by risk, gate low confidence) |
| S6 | process | Two reports: Full Diagnostic + Prioritized Action |
| D1 | decision | 5 - You approve the fixes? |
| S7 | process | 6 - Remediate (snapshot, apply, verify) |
| D2 | decision | Verification passes? |
| S8 | process | Fix kept |
| S9 | process | Auto-rollback (reported honestly) |
| SX | process | Stop - nothing is changed |
| S10| process | 7 - Learn (remember dismissed findings) |
| SE | end     | Done |

## Connections (edges)

```
S0  -> S1
S1  -> S2
S2  -> S3
S3  -> S4
S4  -> S5
S5  -> S6
S6  -> D1
D1  -- No  --> SX
D1  -- Yes --> S7
S7  -> D2
D2  -- Yes --> S8
D2  -- No  --> S9
S8  -> S10
S9  -> S10
SX  -> S10
S10 -> SE
```

## Optional detail — the 7 inspectors inside S3

If you want to expand step S3 instead of collapsing it, the parallel specialists are:
Security, Quality, Logic, Performance, Testing, Supply-chain, Accessibility — each runs
independently and feeds its findings into the Critic gate (S4).

## Note
A PreToolUse safety hook hard-blocks every write until S/D1 approval, so no file changes can
happen before "Yes" at D1. Represent this as a note on the D1 -> S7 edge if the tool supports notes.
