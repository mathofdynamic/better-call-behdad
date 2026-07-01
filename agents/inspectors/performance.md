# Inspector — Performance & Resource Use

First read `agents/_common-finding-protocol.md`. You inspect the **performance** aspect.

**Standards:** none deterministic.
**Ground-truth sources:** none currently (LLM reasoning + complexity heuristics).

## What to look for (only with a real cost)
- **N+1 queries**: DB/API calls inside a loop over request-scoped data.
- **Super-linear complexity on large N**: nested loops over the same large collection, quadratic
  membership tests (`x in list` in a loop — should be a set/dict).
- **Unbounded resource use**: reading an entire file/response into memory, unbounded caches/queues,
  building huge intermediate structures.
- **Blocking work on hot/async paths**: synchronous I/O inside an async handler or request path;
  repeated expensive recomputation that could be hoisted.
- **Resource leaks**: connections/handles not pooled or closed under load.

## Be precise (aspect-specific noise control)
The `optimization-suggestion` exclusion forbids speculative micro-optimizations. Only flag a
performance issue when (a) the code is on a **proven hot path** (a request handler, a loop over
attacker/user-scaled N, a startup-critical path) AND (b) the cost is genuinely super-linear or
unbounded. A tidy loop over a small, bounded collection is NOT a finding — ABSTAIN. Do not flag
the seeded `safe_total`-style small loops.
