# 04 — Multi-Agent Orchestration Patterns

Research brief for **Better-call-behdad**, a multi-agent code-audit skill where a higher-reasoning ORCHESTRATOR/MANAGER coordinates specialized inspector agents (security, quality, logic, etc.) and synthesizes their findings.

**Bottom line up front:** For a code-audit fan-out, the evidence strongly favors an **orchestrator-worker (supervisor) architecture with map-reduce fan-out/fan-in**, typed structured findings, a **consensus/agreement-weighted aggregation** step to dedupe and rank, and a lightweight **adversarial/critic verification** pass on high-severity findings to cut false positives. Reserve the many-agent pattern for tasks whose value justifies a ~4–15x token multiplier, and keep the design as simple as the task allows (Anthropic's central guidance).

---

## 1. Core orchestration patterns

Anthropic's *Building Effective Agents* draws a crucial distinction between **workflows** (LLMs orchestrated through predefined code paths) and **agents** (LLMs dynamically directing their own process). It defines five composable building blocks; the most relevant to a code auditor are below.

### 1.1 Orchestrator-workers (a.k.a. supervisor)
- A central LLM **dynamically decomposes** a task, delegates subtasks to worker LLMs, and **synthesizes** their results.
- Key difference from plain parallelization: subtasks are **not pre-defined** — the orchestrator determines them from the specific input. Anthropic's canonical example is "coding products that make complex changes to multiple files."
- **Fit for Behdad:** This is the backbone pattern. The manager reads the diff/repo, decides which inspectors to spawn and what each should focus on, then merges their reports.

### 1.2 Parallelization — sectioning and voting (map-reduce)
Two sub-modes, both directly applicable:
- **Sectioning:** break work into independent subtasks run in parallel (e.g., one inspector per concern: security, logic, quality, performance; or one per file/module). Aggregate programmatically.
- **Voting:** run the *same* task multiple times to get diverse perspectives and confidence. Anthropic explicitly cites **"code vulnerability reviews across multiple prompts"** and content-safety screening as voting use cases.
- **Map-reduce fan-out/fan-in** is the engineering realization: fan out N subagents/tasks, let each work in an isolated context, then fan in and reduce. In LangGraph this is the **`Send` API** (dynamically invoke a node many times with different states, then aggregate); deferred nodes let you fan-in "at the right moment."

### 1.3 Planner-executor
- A planning LLM produces an explicit, inspectable plan; executor agents carry out each step; a controller loops until done. This is essentially orchestrator-workers with an explicit, persisted plan artifact.
- Anthropic's multi-agent research system operationalizes this: the lead agent **"develops a strategy"** and writes the research plan into **external memory** so it survives the context-window ceiling.
- **Fit for Behdad:** Persist an audit plan (scope, files, which inspectors, budget) so the run is transparent, resumable, and debuggable.

### 1.4 Evaluator-optimizer
- One LLM generates; a second **evaluates against explicit criteria** and returns feedback; loop until the evaluator is satisfied.
- Best "when there are clear evaluation criteria, and when iterative refinement provides measurable value."
- **Fit for Behdad:** Use for report quality — an evaluator checks each finding for a valid file:line, concrete evidence, and a suggested fix, and bounces vague/unsupported findings back for one refinement pass.

### 1.5 Debate / adversarial verification (false-positive reduction)
Not one of Anthropic's five blocks, but a well-studied research pattern that maps onto the "voting/critic" idea and is highly relevant to audit precision:
- **Multi-agent debate:** independent agents challenge and cross-verify each other's claims; if one hallucinates, others can contradict it. Improves factual consistency and reasoning depth.
- **Auditor + critic (prover-skeptic):** the `GPTLENS` pattern has *auditor* agents propose vulnerabilities with reasoning and *critic* agents score/reject them against criteria — directly designed to suppress spurious findings.
- **Consensus with confidence weighting:** independent verifier agents jointly judge an output via majority vote + confidence weighting; reported to achieve near-perfect recall of fabricated claims while keeping false positives low.
- **Caution:** debate can converge on a *confidently wrong* consensus, and naive debate can *amplify* hallucinations. Keep debates short, force each agent to cite evidence (file:line + code snippet), and prefer NLI/tool-grounded contradiction checks over pure opinion exchange.

**Recommendation for Behdad:** don't debate everything (expensive). Gate adversarial verification on **high-severity or low-consensus** findings only — a targeted critic pass, not a full round-robin.

---

## 2. Structuring, deduping, ranking, and synthesizing findings

### 2.1 Typed findings schema
Every inspector should emit machine-parseable findings with a fixed schema so the manager can merge deterministically. A proven field set (drawn from the calimero `ai-code-reviewer` and Anthropic's citation discipline):

```json
{
  "id": "stable-hash",
  "title": "SQL injection via string-concatenated query",
  "severity": "CRITICAL | WARNING | SUGGESTION",   // or critical/high/medium/low/info
  "category": "security | logic | quality | performance | style",
  "file": "src/db/users.py",
  "line": 142,                                       // or line range
  "confidence": 0.0-1.0,
  "evidence": "verbatim code snippet / trace that proves the claim",
  "rationale": "why it is a problem",
  "suggested_fix": "concrete remediation or patch",
  "detected_by": ["security-agent", "logic-agent"], // consensus metadata
  "agreement": 2
}
```

Key discipline: **evidence must be grounded** (exact file:line + snippet). Anthropic's research system uses a dedicated **CitationAgent** post-pass that matches every claim to a source location — the analog here is requiring each finding to point at real code, which is the single biggest lever against hallucinated findings.

### 2.2 Dedupe → consensus → rank (the aggregator)
The calimero multi-agent code reviewer implements exactly the pipeline Behdad needs, in a **"Review Aggregator"** step:
1. **Clustering:** group semantically similar findings across agents (same bug found by security + logic agents collapses to one).
2. **Consensus calculation:** weight each finding by the **agreement ratio** — how many independent agents flagged it. *"Findings are weighted by how many agents agree, reducing false positives."*
3. **Severity ranking:** sort by `severity × agreement_strength` (and confidence). A single-agent low-confidence "SUGGESTION" ranks far below a three-agent "CRITICAL."
4. **Delta tracking / convergence:** across re-runs (e.g., new PR pushes), classify findings as new / fixed / persistent, and **halt when findings stabilize** to save tokens.

### 2.3 How the manager synthesizes conflicting reports
- **Agree → merge & boost confidence.** Overlapping findings raise consensus and rank.
- **Disagree on existence (one flags, others silent).** Treat silence as weak signal, not refutation; keep the finding but lower confidence, and optionally route to a critic/verifier for a tie-break before promoting it to high severity.
- **Disagree on severity/interpretation.** Prefer the **evidence-grounded** claim. Use the evaluator/critic to adjudicate against explicit rubric criteria (accuracy, exploitability, real file:line), mirroring Anthropic's **LLM-as-judge** rubric (factual accuracy, citation accuracy, completeness, source quality).
- **Non-determinism is expected.** Anthropic notes identical inputs yield different runs; design synthesis to be robust to that (stable IDs, idempotent merging, end-state evaluation rather than step matching).

---

## 3. Frameworks

| Framework | Orchestration model | Strengths | Weaknesses / notes |
|---|---|---|---|
| **LangGraph** | Directed graph; agents are nodes sharing a central **state** object; supervisor and hierarchical-team templates; `Send` API for map-reduce fan-out; `Command` for combined state-update + hop; built-in checkpointing/time-travel | Largest production footprint (2026); explicit control, durable state, native fan-out/fan-in, resumability | More boilerplate; you manage graph/state design |
| **CrewAI** | Role-based "crews"; sequential/procedural task pipeline; replay for debugging | Lowest learning curve, fastest prototyping (role DSL, ~20 lines) | Weaker production observability and error recovery; linear model less suited to dynamic fan-out |
| **AutoGen / AG2** | Conversational `GroupChat` among agents; in-memory history | Flexible free-form multi-agent conversation, good for research/prototyping | State is in-memory by default; conversational control can be harder to make deterministic |
| **OpenAI Agents SDK** (successor to experimental **Swarm**, Oct 2024) | Two primitives: **Handoffs** (transfer control, chosen specialist owns the conversation) and **Agents-as-Tools** (`Agent.as_tool()` — a manager calls specialists and owns the final answer) | Clean, opinionated; the **agents-as-tools** pattern maps exactly to a manager that combines specialist outputs | Lighter orchestration; ephemeral context by default; Swarm itself was experimental/narrow |

**Anthropic guidance (framework-agnostic):** *"The most successful implementations weren't using complex frameworks... they were building with simple, composable patterns."* Frameworks can obscure the underlying prompts/responses and complicate debugging — start from direct API calls, add a framework only when it earns its keep. For a Claude Code **skill**, the natural substrate is the **Task/subagent** mechanism (spawn inspector subagents, each with an isolated context, and reduce their structured outputs in the manager) rather than an external orchestration library.

### Anthropic's multi-agent research system — the reference implementation
- **Topology:** lead agent (Opus-class) plans and spawns **3–5 specialized subagents (Sonnet-class) in parallel**; a separate **CitationAgent** does a citation pass; lead synthesizes.
- **Result:** Opus lead + Sonnet subagents beat single-agent Opus by **90.2%** on their internal research eval.
- **Delegation discipline:** each subagent must get an **objective, output format, tool/source guidance, and clear boundaries.** Vague instructions ("research the semiconductor shortage") caused **duplicated work** — the top failure mode for fan-out systems. Scale effort to complexity (1 agent / 3–10 tool calls for simple; 10+ subagents for complex).
- **Parallelism:** running 3–5 subagents and 3+ tool calls concurrently **cut research time up to 90%**.
- **Known limit:** synchronous lead execution blocks on the slowest subagent and can't steer mid-flight; long horizons need summarization + external memory to survive the 200K-token ceiling.

---

## 4. Token-cost and context-window tradeoffs

- **The multiplier:** Anthropic reports agents use ~**4x** the tokens of a single chat, and full **multi-agent systems ~15x**. The cost is running parallel subagents each with their own context window and tool calls.
- **Token budget dominates outcomes:** in Anthropic's browsing evals, **token usage alone explained ~80% of performance variance** — but upgrading the model (e.g., a better Sonnet) beat merely doubling token budget on an older model.
- **Economic gate:** the multiplier only pays off for **high-value tasks with heavy parallelization**, info exceeding a single context window, and many complex tools. It **hurts** on tasks with heavy inter-agent dependencies or shared context — Anthropic explicitly names **most coding tasks** as poorer fits because subtasks are less independent. *Implication for Behdad:* an **audit** (read-only, breadth-first, independent concerns per inspector) is a far better fit than collaborative code-writing — the fan-out is genuinely parallelizable.
- **Context isolation is a feature:** each inspector gets a clean context focused on one concern, avoiding the "context rot" of stuffing security + logic + style into one prompt. The reduce step re-concentrates only the structured findings, not raw transcripts.
- **Cost controls to build in:** cap subagent count and tool calls per severity/scope; use a **cheaper model for cheap concerns** (calimero runs Style on Haiku, everything else on Sonnet); gate the expensive critic/debate pass to high-severity or contested findings; and use **convergence halting** (stop re-review when findings stabilize).

---

## 5. Recommended architectures for Better-call-behdad

### Option A (recommended) — Supervisor + map-reduce fan-out + aggregator + gated critic
- **Manager (high-reasoning, Opus-class):** scopes the audit, writes a persisted plan, and fans out one inspector per concern (security, logic, quality, performance, style), each with an explicit objective/format/boundary and an isolated context.
- **Inspectors (Sonnet-class; Haiku for style):** emit **typed, evidence-grounded findings** (schema in §2.1) in parallel — pure map step.
- **Aggregator (reduce):** cluster/dedupe, compute agreement-weighted consensus, rank by `severity × agreement × confidence` (calimero pattern).
- **Gated critic pass:** run adversarial verification only on CRITICAL or single-agent findings to strip false positives before the final report.
- **Tradeoffs:** best precision/recall and transparency; highest complexity and token cost (~10–15x). Mitigated by model tiering + gating.

### Option B (lean) — Manager-as-tools, single-pass
- Use OpenAI-SDK-style **agents-as-tools** (or Claude subagents): the manager calls each inspector as a tool, owns the final synthesis, no separate debate loop; consensus weighting only.
- **Tradeoffs:** ~4–6x tokens, much simpler, good default for smaller diffs/PRs. Weaker false-positive control (no critic), and synthesis quality rides entirely on the manager prompt.

### Option C — Voting ensemble on a single concern
- For a narrow, high-stakes concern (e.g., security-only), run the **same** inspector prompt N times (voting) and keep only findings above an agreement threshold. This is Anthropic's "code vulnerability review across multiple prompts."
- **Tradeoffs:** simplest to reason about and very effective at cutting false positives for one domain; doesn't give breadth across concerns; N× cost on that concern.

**Guidance:** default to **B** for routine PR-sized audits and **escalate to A** for full-repo or high-stakes audits, borrowing **C**'s voting for the security inspector specifically. In all cases: keep inspector instructions crisp to avoid duplicated work, require grounded evidence for every finding, evaluate on ~20 representative repos/PRs with an LLM-as-judge rubric plus human spot-checks, and instrument tracing since runs are non-deterministic.

---

## Sources

- [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) (orchestrator-workers, parallelization/sectioning/voting, evaluator-optimizer, routing, prompt chaining, simplicity, tool design, when not to use agents)
- [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) (lead/subagent orchestration, delegation discipline, CitationAgent, 15x/4x token economics, 90.2% gain, parallelism, LLM-as-judge eval, context/memory management)
- [calimero-network/ai-code-reviewer (GitHub)](https://github.com/calimero-network/ai-code-reviewer) (specialized inspector agents, typed severities, Review Aggregator: clustering, consensus/confidence weighting, severity ranking, delta/convergence)
- [OpenAI Agents SDK — Multi-agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/) (LLM vs code orchestration, handoffs, agents-as-tools)
- [LangGraph — Multi-agent concepts & Send/Command APIs](https://docs.langchain.com/oss/python/langgraph/use-graph-api) and [Send reference](https://reference.langchain.com/python/langgraph/types/Send) and [langgraph-supervisor](https://reference.langchain.com/python/langgraph-supervisor) (supervisor/hierarchical patterns, map-reduce fan-out/fan-in, shared state, checkpointing)
- [Best Multi-Agent Frameworks 2026 (comparison)](https://gurusup.com/blog/best-multi-agent-frameworks-2026) and [QubitTool framework showdown](https://qubittool.com/blog/ai-agent-framework-comparison-2026) (LangGraph vs CrewAI vs AutoGen/AG2 vs OpenAI SDK: orchestration models, state, production readiness)
- [Minimizing Hallucinations: Adversarial Debate and Voting in LLM Multi-Agents (MDPI Applied Sciences)](https://www.mdpi.com/2076-3417/15/7/3676) and [CSMAD — hallucination detection via multi-agent debate (Amazon Science)](https://www.amazon.science/publications/csmad-hallucination-detection-via-multi-agent-debate-with-nli-verified-contradictory-statements) (cross-verification, consensus + confidence weighting, debate caveats/hallucination amplification)
- [AI-powered Code Review with LLMs (arXiv 2404.18496)](https://arxiv.org/html/2404.18496v2) and [Meta structured prompting for code review (VentureBeat)](https://venturebeat.com/orchestration/metas-new-structured-prompting-technique-makes-llms-significantly-better-at) (auditor/critic scoring, structured findings, review accuracy)
