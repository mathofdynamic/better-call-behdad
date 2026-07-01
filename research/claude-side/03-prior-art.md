# 03 — Prior Art

Survey of existing projects, products, papers, and open-source repos that do AI-driven or
multi-agent code review / auditing / QA. Compiled for **Better-call-behdad**, a multi-agent
code-audit skill. Focus is on *approach*, *open vs closed*, *strengths/weaknesses*, and — most
importantly — **known failure modes** (false positives, hallucinated findings, noise), plus
"what to borrow."

Date of survey: 2026-07-01.

---

## 0. TL;DR — the single most important lesson

Independent, adversarial measurement of AI review agents contradicts vendor marketing.
The strongest empirical study to date (*"From Industry Claims to Empirical Reality"*, arXiv
2604.03196) found that across 13 code-review agents (CRAs), **12 of 13 (92.3%) had an average
signal ratio below 60%**, and that PRs reviewed only by an agent merged far *less* often
(45.2%) than human-reviewed PRs (68.4%) and were abandoned more often (34.9% vs 21.6%). GitHub
Copilot's own review bot scored a **19.8% average signal ratio** in that dataset.

The takeaway for Better-call-behdad: **noise is the enemy, not recall.** Every serious system in
this space now spends most of its engineering on *filtering, grounding, and gating* findings —
not on finding more things. Design the skill around evidence-backed findings, a judge/verifier
gate, severity triage, and "silence is better than noise."

---

## 1. Commercial AI Code-Review Products

### CodeRabbit (closed)
- **Approach:** Assembles 10–15 data points per change (diff, a repo code-graph, linked
  Jira/Linear tickets, CI failure logs, lint output). Cheaper models (GPT-4.1 nano/mini)
  compress each input to cut noise before a frontier model reviews. Runs **40+ linters and
  security scanners**, then an AI reasoning layer validates each static finding in context. A
  **separate "judge" model scores every finding against gathered context and drops ones it can't
  ground.** Generates shell/Python checks (grep, ast-grep) to *prove* an assumption before posting
  a comment. Learns from team feedback (thumbs-down adapts future behavior).
- **Strengths:** Best-in-class grounding pipeline; hybrid static-analysis + LLM; learns team
  conventions; tops some independent benchmarks (Martian).
- **Weaknesses / failure modes:** Independent Lychee audit of 28 PRs (32k+ lines) classified
  comments as **35% quality improvements, 21% nitpicks, 15% useless/noise, 13% wrong assumptions,
  13% thoughtful, 3% security-critical.** So ~28% is nitpick+noise, and 13% rest on *wrong
  assumptions* (hallucinated context). Also a *security* failure mode: Kudelski Security showed a
  malicious PR could achieve RCE + write access across ~1M repos via the review agent's tooling
  (prompt-injection / over-privileged execution).
- **Borrow:** The judge-model gate; generating executable checks to *verify* a finding before
  surfacing it; input compression to reduce context noise; learning from rejections.

### Greptile (closed; v3 built on Anthropic Claude Agent SDK)
- **Approach:** Indexes the entire repo into a **code graph / semantic map** (files, functions,
  dependencies), continuously updated. v3 runs **parallel agents doing multi-hop investigation** —
  tracing dependencies, reading git history, following leads across files. Reads prior human
  review comments to learn standards. Claims "256% better results" and 3x more bugs caught.
- **Strengths:** Best cross-file / whole-codebase context of the cohort; catches issues that
  diff-only tools miss; agentic multi-hop tracing is close to Better-call-behdad's intended model.
- **Weaknesses:** Whole-repo indexing = cost/latency and privacy concerns; more context can mean
  more speculative findings if not gated.
- **Borrow:** Multi-hop cross-file investigation; parallel specialized agents; learning from
  existing review history; building on the same Claude Agent SDK primitives.

### Qodo (formerly CodiumAI) + PR-Agent (PR-Agent is **open source**, Qodo is closed)
- **Approach:** PR-Agent is the original OSS AI PR reviewer (~10k+ stars, donated to community,
  now `PR-Agent` / `qodo-ai/pr-agent` orgs). Slash-command driven (`/review`, `/describe`,
  `/improve`, `/ask`). BYOK across GPT / Claude / Gemini; supports GitHub/GitLab/Bitbucket/Azure
  DevOps. Qodo commercial adds context-aware bug surfacing, free tier, deeper Git integration.
- **Strengths:** Open, hackable, provider-agnostic, well-documented command model — a good
  reference architecture. Explicit "compression" strategy to fit large PRs into context.
- **Weaknesses:** OSS version is comparatively shallow (diff-focused, limited whole-repo context);
  quality depends heavily on the BYOK model.
- **Borrow:** The command/verb decomposition (`review` vs `describe` vs `improve`); provider-agnostic
  design; PR-compression techniques.

### GitHub Copilot Code Review (closed)
- **Approach:** Moved to an **agentic architecture** (2026) with tool-calling to gather repo
  context. 60M+ reviews run. Added grouped suggestions, severity levels, de-duplication.
- **Strengths:** Scale, native GitHub integration, ubiquity.
- **Weaknesses / failure modes:** The canonical **noise cautionary tale.** Maintainers reported
  reviews were "too noisy, most comments low value"; ~15–25% of comments were stylistic
  bikeshedding. 19.8% signal ratio in the independent empirical study. GitHub's own guidance now:
  *"more comments don't mean a better review… silence is better than noise."*
- **Borrow:** Their remediation playbook — severity levels, grouping like comments, dedup, and an
  explicit noise-suppression mandate.

### Amazon CodeGuru Reviewer / Security (closed; being deprecated in favor of Q)
- **Approach:** Hybrid static analysis + ML detectors (resource-leak detector, inconsistency
  detector). Explicitly **prioritizes precision over recall** ("surface only high-confidence
  leaks"); uses build artifacts to check whether an execution path is actually valid.
- **Strengths:** Low false-positive design philosophy; high internal developer-acceptance rate;
  precision-first is exactly the right posture.
- **Weaknesses:** Narrow detector set; Java/Python-centric; no peer-reviewed FP study published;
  largely superseded.
- **Borrow:** *Precision over recall* as an explicit design axiom; validating that a flagged path is
  actually reachable before reporting.

### Sourcery, Codacy, Graphite Diamond, Cursor Bugbot, Ellipsis, Bito, cubic (mostly closed)
- **Sourcery:** AI review + refactoring, 30+ languages, strong on Python, IDE-integrated.
- **Codacy:** Broader quality+security platform (SAST, SCA, DAST, secrets, coverage, quality
  gates) with AI PR review layered on.
- **Graphite Diamond:** "Vigilant senior engineer" contextual PR feedback; notably tuned to flag
  *fewer* issues — some teams find it too conservative (the opposite failure mode: false negatives).
- **Cursor Bugbot:** Deliberately **bug-only** — logic errors, security, race conditions, null
  derefs, edge cases; **intentionally ignores formatting/style.** Reports >70% (up to 76%) of
  flagged bugs resolved before merge; added Autofix cloud agents.
- **Ellipsis:** Lightweight, <5-min setup, review + PR summaries.
- **Bito:** One-click fixes, inline suggestions, 20+ languages, built-in linters.
- **Borrow:** **Cursor Bugbot's scoping discipline** — narrow to real bugs, drop style — is the
  single most-borrowable product decision for a high-signal audit skill. Graphite Diamond is the
  cautionary tale on the other side (too quiet → false negatives). Track a **resolution rate**
  metric (bugs fixed before merge) as the north-star quality signal.

### Semgrep Assistant / Snyk DeepCode AI (closed; the SAST+LLM triage camp)
- **Semgrep Assistant:** LLM+RAG layer that **auto-triages ~60% of new SAST findings**, filtering
  false positives *before* they reach a human; when users audit its triage history they **agree
  96% of the time.** Uses **separate prompt chains** for FP detection vs true-positive reasoning
  (explicitly "not zero-sum"). If it thinks a finding is a FP, it *suppresses* the PR comment.
- **Snyk DeepCode AI:** Hybrid symbolic analysis + ML trained on 25M data-flow cases, 19+
  languages; positioned for AI-generated code.
- **Borrow:** **Separate the "is this a false positive?" judgment from the "why is this real?"
  judgment into distinct passes.** Auto-triage/suppression as a first-class gate. Report a
  human-agreement rate as the quality KPI.

---

## 2. Academic / Research Work

### Empirical reality of code-review agents
- **"From Industry Claims to Empirical Reality: An Empirical Study of Code Review Agents in Pull
  Requests"** (arXiv 2604.03196). *The key paper.* Findings above: 45.2% vs 68.4% merge rate;
  34.9% vs 21.6% abandonment; 60.2% of agent-only PRs sat in the 0–30% (noisy) signal band; 92.3%
  of agents averaged <60% signal; Copilot 19.8%, GitHub Advanced Security bot 27.6%. Directly
  refutes the "80% of PRs need no human comment" marketing claim.
- **"AI-powered Code Review with LLMs: Early Results"** (arXiv 2404.18496). A 4-agent system
  (review / bug-detection / code-smell / optimization). Reported LLMs caught issues static tools
  missed and gave better explanations — but **published no failure-mode or FP analysis** (a common
  gap: early academic systems rarely quantify their own noise).
- **Survey of Code Review Benchmarks** (arXiv 2602.13377): 99 papers, 2015–2025, pre-LLM vs LLM
  era — useful for benchmark/metric selection.

### LLM vulnerability detection
- **IRIS** (ICLR 2025, `iris-sast/iris`, **open source**): neuro-symbolic — LLM infers taint
  specs, static analysis (CodeQL) executes whole-repo reasoning. Detected **55 vulns vs CodeQL's
  27**; found 4 previously-unknown vulns in real Java projects. **But the honest number: average
  false-discovery rate of ~84.8%** (only 5.2 points better than CodeQL). I.e., even SOTA
  LLM-assisted detection is *mostly false positives* without a strong human/verifier gate. F1
  improved only ~0.1.
- **"Reducing False Positives in Static Bug Detection with LLMs: An Empirical Study in Industry"**
  (arXiv 2601.18844) and **SAST-Genius** (cut FPs 225 → 20): the reproducible finding is that
  LLMs are far better as a **triage/filter layer on top of a sound static analyzer** than as
  primary detectors.
- **"Let the Trial Begin: A Mock-Court Approach"** (arXiv 2505.10961): adversarial multi-agent
  (prosecution/defense/judge) for vuln detection — a concrete pattern for reducing overconfident
  findings.
- **ZeroDayBench**, **CWE-Bench-Java** — evaluation datasets worth targeting.

### Automated Program Repair (APR) / agentic bug fixing
- Systems: **SWE-Agent, OpenHands, AutoCodeRover, RepairAgent, SWE-Search (MCTS), SWE-RL** — all
  beat one-shot prompting by giving the LLM *tools* (grep, compile, run tests, edit) in a ReAct
  loop. Benchmarks: SWE-bench / Lite / Verified, SWT-Bench.
- **"LLM-based Agents for Automated Bug Fixing: How Far Are We?"** (arXiv 2411.10213): agents
  still fail on complex multi-file bugs; success is brittle.
- **Google-scale APR finding:** dual-LLM policies (one for *bug abstention* — deciding NOT to
  act — and one for *patch validation*) gave a **+39 percentage-point** absolute increase in
  filtered success. Lesson: an explicit *abstain* action and a *validate* action are worth more
  than a smarter generator.
- **"Dynamic Cogeneration of Bug Reproduction Test in Agentic Program Repair"** (arXiv 2601.19066):
  auto-writing a failing repro test before fixing — a strong grounding technique.

### Multi-agent debate / consensus (directly relevant to a "multi-agent" audit skill)
- Multi-agent debate + voting can cut hallucinations (reports of up to ~40% reduction) **only when
  every claim is grounded in an independently verified source** and a peer-review cycle isolates
  false statements early.
- **Caution, well-documented:** (a) "LLMs Cannot Self-Correct Reasoning Yet" (arXiv 2310.01798) —
  self-correction without external signal often *degrades* results; (b) multi-agent debate does
  **not** reliably beat simple self-consistency; (c) homogeneous agent pools cause premature
  convergence and unfair self-judging; (d) debate can **amplify** hallucinations rather than damp
  them ("Hallucination Amplification in Multi-Agent Debate").
- **Borrow / avoid:** Multi-agent only helps if agents are *heterogeneous*, claims are *grounded in
  tool-verified evidence*, and there's an independent judge. Do not rely on agents "debating" their
  way to truth without external verification — that's a documented failure mode.

---

## 3. Open-Source: Claude Code Skills / Subagents / MCP / Codex

### Directly relevant reference implementations
- **`anthropics/claude-code-security-review`** (~5.2k stars, **open**): AI security-review GitHub
  Action. Semantic diff analysis → contextual review → findings with severity + remediation →
  **multi-layered false-positive filtering** → PR comments. **Explicitly excludes FP-prone
  categories** (DoS, rate-limiting, resource exhaustion, generic input-validation without proven
  impact, open-redirect). Supports a **custom FP-filtering instructions file**. Documented
  limitation: **not hardened against prompt injection — trusted PRs only.** Closest official
  analog to Better-call-behdad.
- **`trailofbits/skills`** (**open**): a dozen+ pro security-audit Claude Code skills. Approach
  emphasizes **structured noise reduction**: clustered parallel workers, **SARIF-standardized
  output**, pattern-based variant analysis, and — critically — **"false-positive verification with
  mandatory gate reviews"** before a finding is accepted. Skills include differential review,
  C/C++/Rust analysis, constant-time analysis, mutation/property testing, supply-chain audit. Best
  open blueprint for gated, evidence-driven findings.
- **`VoltAgent/awesome-claude-code-subagents`** (**open**, 100+/154+ subagents): category
  `04-quality-security` has `security-auditor`, `code-reviewer`, `architect-reviewer`,
  `compliance-auditor`, `ad-security-reviewer`. Each runs in an **isolated context** to prevent
  cross-contamination. Good for prompt/persona patterns; quality varies, little independent
  validation.

### Curated lists & other collections
- `rohitg00/awesome-claude-code-toolkit` — 135 agents / 35 skills / commands; includes REVIEW/QA/
  DEBUG modes, "6-layer OWASP+ security with bash-guard and secret scanning," PR-risk-review skills.
- `efij/awesome-claude-code-security`, `jqueryscript/awesome-claude-code`,
  `hesreallyhim/awesome-claude-code`, `hashgraph-online/awesome-codex-plugins` (Codex side),
  `GetBindu/awesome-claude-code-and-skills`.

### MCP servers for security/audit
- `Sengtocxoen/sast-mcp` — wraps multiple SAST tools for Claude Code.
- `awslabs/automated-security-helper` (ASH) — OSS SAST/SCA/IaC orchestrator with an MCP server.
- `qianniuspace/mcp-security-audit` — npm-dependency vuln auditing over MCP.
- `blackkhawkk/mcp_sast_sca_sbom` — SAST/SCA/SBOM/secrets framework.
- `ModelContextProtocol-Security/mcpserver-audit` + `slowmist/MCP-Security-Checklist` — auditing the
  *MCP servers themselves* (relevant to Better-call-behdad's own supply-chain/prompt-injection risk).
- **Borrow:** Orchestrate *real* deterministic scanners (Semgrep, CodeQL, linters, secret scanners)
  via MCP and use the LLM as the *reasoning + triage + evidence* layer, not the primary detector —
  the pattern that consistently wins in both industry and academia.

---

## 4. Comparison Table

| Name | Approach | Open/Closed | Strengths | Weaknesses / Failure Modes | What to Borrow |
|------|----------|-------------|-----------|----------------------------|----------------|
| **CodeRabbit** | Multi-input + code-graph + 40+ scanners; separate judge model grounds every finding; generates grep/ast-grep proofs | Closed | Strong grounding; hybrid; learns from rejects | 28% nitpick/noise, 13% wrong-assumption (Lychee); RCE via prompt injection (Kudelski) | Judge-model gate; executable proof-before-comment; learn from thumbs-down |
| **Greptile v3** | Whole-repo code graph; parallel multi-hop agents on Claude Agent SDK | Closed | Best cross-file context; agentic tracing | Cost/latency/privacy; speculative findings if ungated | Multi-hop cross-file investigation; parallel specialized agents |
| **PR-Agent / Qodo** | Slash-command verbs; BYOK; PR compression | PR-Agent **open**, Qodo closed | Hackable, provider-agnostic reference arch | OSS version shallow, diff-only | Verb decomposition; provider-agnostic design |
| **Copilot Code Review** | Agentic tool-calling; severity + grouping | Closed | Scale, native GH | **19.8% signal ratio**; noisy, bikeshedding | Noise remediation: severity, grouping, dedup, "silence>noise" |
| **CodeGuru** | Hybrid ML detectors; precision-first; path-validity via build artifacts | Closed | Low-FP philosophy; high acceptance | Narrow, Java/Python, deprecated | **Precision over recall**; check path reachability |
| **Cursor Bugbot** | Bug-only; ignores style; Autofix agents | Closed | Narrow scope → high signal; 70–76% resolved | Misses non-bug quality issues by design | **Scope to real bugs, drop style**; track resolution rate |
| **Graphite Diamond** | Contextual "senior engineer" review, conservative | Closed | Low noise | Too quiet → false negatives | Tunable verbosity, but watch the FN edge |
| **Semgrep Assistant** | LLM+RAG triage on SAST; separate FP vs TP prompt chains; suppresses FP comments | Closed | Auto-triages 60% FPs; 96% human agreement | Depends on Semgrep rules underneath | **Separate FP-judgment from TP-reasoning**; suppress before human sees |
| **Snyk DeepCode AI** | Symbolic + ML, 25M flows | Closed | Strong dataflow; AI-code focus | Closed, model opacity | Hybrid symbolic+ML detection |
| **IRIS** | Neuro-symbolic: LLM taint specs + CodeQL | **Open** | 2x CodeQL recall; found real 0-days | **~85% false-discovery rate**; needs human gate | LLM-infers-specs, static-engine-executes split |
| **SAST-Genius / FP-reduction studies** | LLM as triage layer over static analyzer | Research | FPs 225→20 | Only as good as base analyzer | LLM as filter, not primary detector |
| **Mock-Court / multi-agent debate** | Prosecution/defense/judge; voting | Research | Can cut hallucination ~40% *if grounded* | Amplifies hallucination w/ homogeneous agents; debate ≯ self-consistency; self-correction can hurt | Heterogeneous agents + grounded claims + independent judge only |
| **Agentic APR (SWE-Agent, Google dual-LLM)** | ReAct loop with tools; abstain + validate policies | Mixed (SWE-Agent open) | Repro-test grounding; +39pp with validation gate | Brittle on multi-file bugs | **Explicit abstain action + patch validator**; write failing repro test first |
| **anthropics/claude-code-security-review** | Semantic diff review; multi-layer FP filter; excludes FP-prone categories | **Open** | Official; category-level FP exclusion; custom filter file | **Not prompt-injection hardened** (trusted PRs only) | Category exclusion list; custom FP-filter file; severity+remediation format |
| **trailofbits/skills** | Clustered parallel workers; SARIF; mandatory FP gate reviews | **Open** | Pro-grade; gated findings; standardized output | Security-expert-oriented, setup heavy | **Mandatory gate review before accepting a finding**; SARIF output; variant analysis |
| **VoltAgent subagents** | Persona subagents in isolated contexts | **Open** | Ready personas; context isolation | Uneven quality, unvalidated | Isolated-context subagents; persona prompts |
| **MCP SAST servers (sast-mcp, ASH, etc.)** | Wrap deterministic scanners behind MCP | **Open** | Real tools + LLM reasoning | Orchestration complexity | LLM = reasoning/triage layer over deterministic scanners |

---

## 5. Synthesized design implications for Better-call-behdad

1. **Noise is the product risk, not recall.** 92% of measured agents run <60% signal; Copilot at
   ~20%. Optimize for signal ratio and *resolution rate*, not finding count.
2. **Grounding beats cleverness.** Every winning system makes the model *prove* a finding —
   executable checks (CodeRabbit's grep/ast-grep), failing repro tests (agentic APR), path
   reachability (CodeGuru), or a static-analyzer's dataflow (IRIS/Semgrep). Require evidence per
   finding.
3. **Two separate judgments.** Split "is this a false positive?" (suppression gate, à la Semgrep /
   Trail of Bits mandatory gate review) from "why is this real?" (explanation). Add an explicit
   **abstain** option (Google's +39pp).
4. **Scope discipline.** Bugbot's bug-only stance yields the best signal. Categorically exclude
   FP-prone classes up front (as the Anthropic action does), and drop pure style/bikeshedding.
5. **Multi-agent only with heterogeneity + external verification.** Debate/consensus can *amplify*
   hallucinations; use diverse agents, ground every claim in tool output, and add an independent
   judge — don't let agents vote themselves into confidence.
6. **Orchestrate real scanners.** Use deterministic tools (Semgrep, CodeQL, linters, secret
   scanners) via MCP as the substrate; the LLM adds context, triage, and remediation.
7. **Harden against prompt injection.** Both the Anthropic action and the CodeRabbit RCE incident
   flag this as *the* security failure mode for review agents that execute tooling on untrusted
   diffs. Treat reviewed code as hostile input.
8. **Learn from rejections** (CodeRabbit/Greptile) and **standardize output** (Trail of Bits SARIF,
   Copilot severity+grouping+dedup).

---

## 6. Sources / Links

**Products**
- CodeRabbit — how it works: https://www.coderabbit.ai/blog/how-coderabbit-delivers-accurate-ai-code-reviews-on-massive-codebases
- CodeRabbit — static analysis + AI: https://www.coderabbit.ai/blog/boosting-static-analysis-accuracy-with-ai
- CodeRabbit pipeline explainer: https://theaiengineer.substack.com/p/how-coderabbit-actually-works
- Lychee independent audit of CodeRabbit: https://lycheeorg.dev/2025-09-13-code-rabbit/
- Kudelski — CodeRabbit RCE / write access to ~1M repos: https://kudelskisecurity.com/research/how-we-exploited-coderabbit-from-a-simple-pr-to-rce-and-write-access-on-1m-repositories
- Greptile Agent: https://www.greptile.com/agent
- Greptile v3 (Claude Agent SDK): https://www.greptile.com/blog/greptile-v3-agentic-code-review
- Greptile — reviews need context: https://www.greptile.com/blog/ai-reviews-need-context
- PR-Agent (OSS): https://github.com/qodo-ai/pr-agent
- Qodo: https://www.qodo.ai/
- GitHub Copilot — 60M reviews / noise: https://github.blog/ai-and-ml/github-copilot/60-million-copilot-code-reviews-and-counting/
- Copilot agentic architecture: https://github.blog/changelog/2026-03-05-copilot-code-review-now-runs-on-an-agentic-architecture/
- Amazon CodeGuru — how it works: https://docs.aws.amazon.com/codeguru/latest/reviewer-ug/how-codeguru-reviewer-works.html
- CodeGuru resource-leak detector: https://aws.amazon.com/blogs/devops/resource-leak-detection-in-amazon-codeguru/
- Sourcery / Codacy / Diamond comparisons: https://www.devtoolsacademy.com/blog/state-of-ai-code-review-tools-2025/
- Cursor Bugbot: https://cursor.com/bugbot
- Bugbot alternatives (Ellipsis/Bito/Greptile notes): https://www.getpanto.ai/blog/cursor-bugbot-alternatives
- Semgrep Assistant — 60% triage: https://semgrep.dev/blog/2025/semgrep-is-confidently-handling-60-of-all-triage-for-users-without-reducing-coverage/
- Semgrep — 96% researcher agreement: https://semgrep.dev/blog/2025/building-an-appsec-ai-that-security-researchers-agree-with-96-of-the-time/
- Snyk DeepCode AI (comparison): https://sanj.dev/post/ai-code-security-tools-comparison/

**Academic**
- From Industry Claims to Empirical Reality (empirical CRA study): https://arxiv.org/pdf/2604.03196
- AI-powered Code Review with LLMs, Early Results: https://arxiv.org/html/2404.18496v2
- Survey of Code Review Benchmarks (pre-LLM vs LLM): https://arxiv.org/html/2602.13377v1
- IRIS (ICLR 2025): https://openreview.net/forum?id=9LdJDU7E91 — code: https://github.com/iris-sast/iris
- Reducing False Positives in Static Bug Detection with LLMs (industry): https://arxiv.org/pdf/2601.18844
- Mock-Court multi-agent vuln detection: https://arxiv.org/pdf/2505.10961
- Survey of LLM-based APR: https://arxiv.org/html/2506.23749v1
- LLM Agents for Bug Fixing: How Far Are We?: https://arxiv.org/html/2411.10213v2
- Bug reproduction test cogeneration (agentic APR): https://arxiv.org/pdf/2601.19066
- SWE-Bench in APR (what's in a benchmark): https://arxiv.org/pdf/2602.04449
- Multi-agent debate hallucination amplification: https://corpora.ai/reports/validate/29-v-a-12-hallucination-amplification-in-multi-agent-debate.html
- LLMs Cannot Self-Correct Reasoning Yet: https://arxiv.org/pdf/2310.01798
- Adversarial debate + voting to minimize hallucinations: https://www.mdpi.com/2076-3417/15/7/3676

**Open source / skills / MCP**
- anthropics/claude-code-security-review: https://github.com/anthropics/claude-code-security-review
- trailofbits/skills: https://github.com/trailofbits/skills
- VoltAgent/awesome-claude-code-subagents (04-quality-security): https://github.com/VoltAgent/awesome-claude-code-subagents/tree/main/categories/04-quality-security
- rohitg00/awesome-claude-code-toolkit: https://github.com/rohitg00/awesome-claude-code-toolkit
- efij/awesome-claude-code-security: https://github.com/efij/awesome-claude-code-security
- Sengtocxoen/sast-mcp: https://github.com/Sengtocxoen/sast-mcp
- awslabs/automated-security-helper (ASH): https://github.com/awslabs/automated-security-helper
- qianniuspace/mcp-security-audit: https://github.com/qianniuspace/mcp-security-audit
- ModelContextProtocol-Security/mcpserver-audit: https://github.com/ModelContextProtocol-Security/mcpserver-audit
- slowmist/MCP-Security-Checklist: https://github.com/slowmist/MCP-Security-Checklist
- hashgraph-online/awesome-codex-plugins: https://github.com/hashgraph-online/awesome-codex-plugins
