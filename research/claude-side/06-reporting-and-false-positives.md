# 06 — Reporting, Human-in-the-Loop & False-Positive Reduction

Research brief for **Better-call-behdad**, a multi-agent code-audit skill that
produces developer-facing reports and asks for confirmation before applying
fixes. This document covers (1) severity taxonomies and prioritization, (2)
presenting findings so developers actually understand and act, (3) safe
confirmation-before-fix workflows, and (4) — the critical section —
false-positive / hallucination reduction in AI code review.

---

## 1. Severity Taxonomies & Prioritizing Findings

### 1.1 CVSS — severity, not risk

- **CVSS (Common Vulnerability Scoring System)** produces a 0–10 severity score
  from static, intrinsic characteristics of a vulnerability (attack vector,
  complexity, privileges required, impact to Confidentiality/Integrity/
  Availability). It is maintained by FIRST and used by NVD.
- **Key caveat repeated across sources: CVSS measures *technical severity*, not
  *risk*.** It ignores whether the component is actually reachable, exposed to
  the internet, authenticated, or business-critical. A "Critical" CVSS finding
  in an unexposed internal component may carry near-zero real risk; a "Medium"
  in a customer-facing path may be urgent.
- Practical implication for the skill: **do not present a raw CVSS number as if
  it were a priority.** Treat it as one input.

### 1.2 EPSS — likelihood of exploitation

- **EPSS (Exploit Prediction Scoring System)**, also from FIRST, is an ML model
  trained on exploit-code availability, threat-intel feeds, honeypot data, and
  attacker behavior. It outputs a **probability (0–1) that a vuln will be
  exploited in the wild in the next 30 days**, updated daily.
- CVSS answers "how bad if exploited?"; EPSS answers "how likely to be
  exploited?". EPSS data refutes the assumption that attackers only target
  high-CVSS issues. **Recommended: use them together** (severity × probability),
  optionally gated by reachability/exposure context (Risk-Based Vulnerability
  Management, RBVM).

### 1.3 Likelihood × Impact matrices (OWASP Risk Rating)

The OWASP Risk Rating Methodology is the most directly applicable model for a
code-audit tool because it decomposes risk into estimable sub-factors rather
than a single opaque score. **RISK = Likelihood × Impact.**

- **Likelihood** = average of:
  - *Threat-agent factors*: Skill Level, Motive, Opportunity, Size.
  - *Vulnerability factors*: Ease of Discovery, Ease of Exploit, Awareness,
    Intrusion Detection.
- **Impact** = 
  - *Technical impact*: Loss of Confidentiality, Integrity, Availability,
    Accountability.
  - *Business impact*: Financial Damage, Reputation Damage, Non-Compliance,
    Privacy Violation.
- Each factor is rated 0–9; averages map to Low / Medium / High, and the
  Likelihood×Impact grid yields an overall Critical/High/Medium/Low/Note.

### 1.4 Prioritization guidance for the skill

- **Blend three signals**: technical severity (CVSS-style), exploitability/
  likelihood (EPSS-style or OWASP likelihood factors), and **contextual
  exposure/reachability** (is this code path actually reachable / on the
  attack surface?). Reachability is something an agent with repo context can
  reason about — a real differentiator.
- **Prioritize on *validated exposure*, not inherited severity scores.** Active,
  reachable risk moves first; theoretical risk is scheduled.
- **Avoid diluting the report** with low-value informational findings — they
  bury the critical ones (see §2).
- A defensible taxonomy for the report: `Critical / High / Medium / Low / Info`,
  where each finding carries **both** a severity label **and** a short
  justification of likelihood + impact + reachability, plus a confidence score
  (see §4).

---

## 2. Presenting Findings to Developers Who "Don't Know What They Don't Know"

### 2.1 Report structure (layered by audience)

- Use a **layered structure**: executive summary (risk landscape, counts by
  severity) → detailed findings → actionable recommendations. Tailor depth to
  audience; a solo developer needs the "why it matters" plain-language layer
  that a senior security engineer would skip.
- Each finding should be **self-contained**: what, where (file:line), why it's a
  risk (in plain terms), how to fix, and how confident the tool is.

### 2.2 Make every finding actionable

- **Every finding must include at least one specific, concrete fix** — not
  generic advice. "Apply patches", "restrict access", "harden config" are
  anti-patterns: without exact change specs, developers interpret findings
  inconsistently. Specify *which* change, *where*.
- **Prefer diff/patch proposals over prose.** A concrete before→after diff (a)
  removes ambiguity, (b) lets the developer evaluate the fix at a glance, and
  (c) feeds directly into a staged/confirm-before-apply workflow (§3).
- **Explain the risk in context**: trace the finding to the code path, the data
  it touches, and a realistic exploitation/failure scenario. This is what closes
  the "don't know what they don't know" gap — the developer learns the *class*
  of problem, not just the single line.
- **Assign ownership / next action.** For a solo-dev tool this is lighter, but
  each finding should map to a single clear next step.

### 2.3 Closure / verification

- A fix isn't "done" until it's **tested against the original failure
  condition** — if the vulnerable condition still exists, the finding reopens.
  For the skill, this argues for a **re-audit / verification pass after a fix is
  applied**, not just marking it resolved.

---

## 3. Safe Confirmation-Before-Fix Workflows (Human-in-the-Loop)

Human-in-the-loop (HITL): a human approves, rejects, or modifies AI output at
critical checkpoints **before it takes effect**. Core patterns and pitfalls:

### 3.1 Where to put the gate

- **Gate irreversible / high-blast-radius actions behind pre-action approval.**
  Canonical "always gate" categories: deploying to prod, external
  communications, financial actions, **deleting data, changing privileges** —
  and, for a code tool, **writing to the working tree / committing / pushing**.
- Reversible actions (e.g., generating a report, a dry-run) can run freely.

### 3.2 Approval-gate design

- **Replace a bare "Approve?" with a checklist**: intent, affected files/scope,
  expected blast radius, and rollback plan. The approver positively
  acknowledges what will change.
- Show the **exact diff** to be applied — approval should be over concrete
  changes, not a vague intent.
- Consider **"two-factor judgment"** on the riskiest changes: an independent
  second review or a counter-model sanity check before execution.

### 3.3 Dry-run → staged → apply → verify → rollback

- **Dry-run first**: propose the change (draft the patch / command) and pause;
  the human reviews target, scope, and diff before anything executes.
- **Stage changes** rather than applying in place — e.g., write to a branch /
  worktree / patch file so nothing is destructive until confirmed.
- **Post-action verification**: "an approval doesn't guarantee success, and
  success doesn't guarantee correctness." After applying, **re-run
  tests/linters/the audit** and log the outcome. Re-verify that the fix closed
  the original finding.
- **Always define a rollback path** (git revert / stash / restore the staged
  copy) and surface it before applying.

### 3.4 Critical implementation pitfalls (from production HITL guidance)

- **Approvals must happen *before* side effects, not after** — otherwise it's
  just retrospective review.
- **Idempotency**: retries (timeouts, restarts) can double-apply an approved
  action. Use idempotency keys + execution-time checks that the action hasn't
  already happened.
- **Never let the model decide whether its own action needs approval.** A
  persuasive prompt or prompt injection can talk it out of asking. **The gate
  must fire based on *what the action is* (write/delete/commit), enforced at the
  workflow/execution layer — not on what the model inferred.**
- **Log the full decision trail** (proposal, approver, diff, outcome) for
  auditability.

---

## 4. False-Positive / Hallucination Reduction in AI Code Review *(critical section)*

### 4.1 Why LLMs hallucinate findings

- **Training incentives reward confident guessing over acknowledging
  uncertainty** (per OpenAI's own research: "training and evaluation procedures
  reward guessing over acknowledging uncertainty"). Models are optimized to be
  confident test-takers, not careful reasoners.
- Hallucination is worse **outside the training distribution** and is argued to
  be structurally inevitable, not a patchable bug — so mitigation must be
  *architectural*, not just prompt-tuning.
- Concrete manifestations relevant to code review:
  - **Fabricated APIs / parameters / identifiers** — "Knowledge-Conflicting
    Hallucinations": subtle semantic errors (non-existent API params, misused
    identifiers) that evade linters. (Package fabrication: ~19.7% of
    recommended packages in one study didn't exist; ~86.6% of GPT-4 references
    were partly/entirely invented.)
  - **Diff-only tunnel vision**: reviewing a hunk without the surrounding
    call-chain leads to "bugs" that aren't bugs once you see the caller.
  - **Confident false positives**: flagging correct code as broken.

### 4.2 Grounding in deterministic tools (the single highest-leverage lever)

- **Run real static analysis / linters / SAST as the substrate, and use the LLM
  as a *reasoning/filter* layer on top** — not the sole detector. Deterministic
  tools give ground truth the LLM can't fabricate.
- **Deterministic AST / signature checks eliminate whole hallucination
  classes**: parse generated or reviewed code into an AST, cross-reference every
  used identifier against definitions in scope, and validate every API call
  against ground-truth library signatures. One arXiv framework reports **100%
  precision / zero false positives** for the hallucination classes it targets.
- **Hybrid LLM + SAST** frameworks report large precision gains (~89.5% in one
  study; IRIS-style hybrids detecting 55 vulns vs CodeQL's 27).
- **Generate verification scripts / "receipts."** Before posting a finding, have
  the agent emit and run a concrete check (grep, `ast-grep`, a small
  script/test) that proves the claim from the actual codebase. "Comments come
  with receipts" → less noise. This is directly implementable in an agentic
  skill with a shell tool.

### 4.3 Adversarial / agentic verification (second-pass)

- **Judge / verifier model**: a *separate* pass scores each candidate finding
  against gathered context and **drops findings it cannot ground.** CodeRabbit
  attributes its low false-positive rate largely to this judge step.
- **Follow the call chain to confirm before flagging.** Greptile's agentic
  approach (built on the Anthropic Claude Agent SDK in v3) has the agent
  autonomously investigate — follow references/callers — to decide whether a
  concern is real or a false positive, "sharply reducing noise vs diff-only
  tools." Their v4 reports comment acceptance rising from 30%→43% and ~68% more
  positive developer replies, driven mainly by FP reduction.
- **Chain-of-Verification (CoVe)**: generate → plan verification questions →
  answer them independently → produce the verified finding. Reported ~28%
  precision improvement.
- **Multi-agent generate + cross-validate**: separate generator and validator
  agents improved consistency ~85.5% and reduced false positives ~25.8% in one
  study.

### 4.4 Self-consistency / voting & confidence scoring

- **Self-consistency**: sample the review multiple times and keep the finding
  only if it recurs (majority vote). Rationale: **correct findings appear
  consistently across samples; hallucinations have higher variance.** (SC lifted
  GSM8K reasoning accuracy ~17.9%.) Cost scales with sample count — consider
  dynamic sampling (more samples only for uncertain findings).
- **Confidence scoring + calibration**: have the judge emit a confidence per
  finding; run **multiple judge passes and aggregate by majority vote**, report
  average confidence. **Calibrate the judge against human corrections** — sample
  the judgments, have a human correct disagreements, treat those as ground
  truth, and tune the rubric until agreement is high. Only then trust it at
  scale.
- **Grounding verification as an explicit judge dimension** (à la MLflow's
  built-in judges): score whether a finding is grounded in retrieved code vs.
  filled in from the model's own training. Findings that aren't grounded get
  suppressed or down-ranked.

### 4.5 Context engineering & learning

- **Full-repo / semantic index + codegraph** (dependency mapping) so the model
  reasons over the *real* code, related files, configs, tests, and history —
  not just the diff. Grounding in a repo index also makes results **more
  repeatable** against LLM stochasticity.
- **Persist "learnings"** from developer feedback (e.g., "auto-generated
  migrations are exempt") to suppress recurring false positives on future runs.
- **Configurable severity thresholds** so the team can tune the
  signal-to-noise ratio.

### 4.6 The precision/recall trade-off (design tension to state explicitly)

Independent 2026 benchmarks make the trade-off concrete: Greptile caught ~82% of
bugs but produced ~11 false positives per run; CodeRabbit caught ~44% but only
~2 false positives. **For a confirm-before-fix tool aimed at developers who
"don't know what they don't know," precision (trust) usually matters more than
recall** — a noisy tool gets ignored, and worse, a wrong auto-proposed fix
applied on approval is actively harmful. Design toward **high-confidence,
grounded, verified findings**, expose confidence, and let the user opt into a
higher-recall "paranoid" mode.

### 4.7 Recommended layered pipeline for Better-call-behdad

1. **Deterministic first**: run linters / SAST / type-checkers / AST checks →
   ground truth.
2. **LLM reasoning layer**: interpret, add context, and generate candidate
   findings + proposed diffs.
3. **Agentic verification**: for each candidate, follow the call chain and/or
   run a generated proof script; drop what can't be grounded.
4. **Judge pass + confidence**: separate model scores grounding/severity;
   optionally self-consistency vote; attach a calibrated confidence.
5. **Rank & filter**: severity × likelihood × reachability, threshold on
   confidence, cap the count to avoid dilution.
6. **Report**: layered, plain-language risk + concrete diff per finding.
7. **HITL gate**: dry-run → show diff → checklist approval → staged apply →
   re-verify → rollback path. Gate enforced by action type at the execution
   layer.
8. **Learn**: record dismissals to suppress future false positives.

---

## Sources / Links

**Severity & prioritization**
- FIRST/NVD CVSS — https://nvd.nist.gov/vuln-metrics/cvss ; https://en.wikipedia.org/wiki/Common_Vulnerability_Scoring_System
- Red Hat, "CVSS vs. Risk" — https://www.redhat.com/en/blog/common-vulnerability-scoring-system-cvss-vs-risk-why-are-we-still-having-conversation
- Safe Security, understanding CVSS — https://safe.security/resources/insights/understanding-cvss-scores/
- OWASP Risk Rating Methodology — https://owasp.org/www-community/OWASP_Risk_Rating_Methodology ; https://www.simplerisk.com/blog/owasp-risk-rating-methodology-and-simplerisk
- EPSS vs CVSS — https://www.intruder.io/blog/epss-vs-cvss ; https://www.splunk.com/en_us/blog/learn/epss-exploit-prediction-scoring-system.html ; https://cloudsmith.com/blog/vulnerability-scoring-systems ; https://www.brinqa.com/blog/epss-vs-cvss

**Presenting findings / remediation**
- Wiz, "What Is a Penetration Testing Report?" — https://www.wiz.io/academy/vulnerability-management/penetration-testing-report
- Hyperproof, remediating audit findings — https://hyperproof.io/resource/audit-findings-remediation-efforts/
- Falcony, prioritization & remediation — https://blog.falcony.io/en/exploring-security-audit-findings-prioritization-and-remediation-strategies
- Springer, "How to Write an Effective Cybersecurity Audit Report" — https://link.springer.com/chapter/10.1007/979-8-8688-1712-0_7

**Human-in-the-loop / approval workflows**
- Digital Applied, HITL escalation design (2026) — https://www.digitalapplied.com/blog/human-in-the-loop-escalation-design-ai-agents-2026
- StackAI, approval workflows — https://www.stackai.com/insights/human-in-the-loop-ai-agents-how-to-design-approval-workflows-for-safe-and-scalable-automation
- Agno, HITL controls in production — https://www.agno.com/blog/how-to-add-human-in-the-loop-controls-to-ai-agents-that-actually-run-in-production
- Cloudflare Agents, HITL patterns — https://developers.cloudflare.com/agents/concepts/agentic-patterns/human-in-the-loop/
- Permit.io, HITL best practices — https://www.permit.io/blog/human-in-the-loop-for-ai-agents-best-practices-frameworks-use-cases-and-demo

**False-positive / hallucination reduction**
- CodeRabbit, accurate reviews on massive codebases — https://www.coderabbit.ai/blog/how-coderabbit-delivers-accurate-ai-code-reviews-on-massive-codebases
- CodeRabbit, boosting static analysis accuracy with AI — https://www.coderabbit.ai/blog/boosting-static-analysis-accuracy-with-ai
- Greptile, what is AI code review — https://www.greptile.com/what-is-ai-code-review ; benchmarks — https://www.greptile.com/benchmarks
- DEV, "Best AI Code Reviewer in 2026 (146 PRs, 679 findings)" — https://dev.to/_vjk/best-ai-code-reviewer-in-2026-we-ran-4-in-parallel-for-3-weeks-146-prs-679-findings-1c0f
- diffray, "LLM Hallucinations in AI Code Review" — https://diffray.ai/blog/llm-hallucinations-code-review/
- arXiv, "Detecting and Correcting Hallucinations in LLM-Generated Code via Deterministic AST Analysis" — https://arxiv.org/html/2601.19106v1
- arXiv, "Beyond Functional Correctness: Exploring Hallucinations in LLM-Generated Code" — https://arxiv.org/pdf/2404.00971
- arXiv, self-consistency for reasoning/hallucination — https://arxiv.org/pdf/2504.09440 ; https://arxiv.org/pdf/2505.09031 (CoT+RAG+SC+self-verification)
- LangChain, calibrating LLM-as-Judge with human corrections — https://www.langchain.com/resources/llm-as-a-judge
- MLflow, LLM-as-a-Judge (grounding/correctness judges) — https://mlflow.org/llm-as-a-judge
