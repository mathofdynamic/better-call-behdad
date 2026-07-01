1. Objective Standards and Evaluation Rubrics
To ensure the multi-agent system provides actionable feedback rather than subjective reviews, all evaluations must be grounded in industry-standard engineering rubrics. The sub-agents enforce these objective baselines across security, code quality, test coverage, and compliance.   

Security and Supply Chain Baselines
Security verification requires a hybrid strategy that combines pattern-based signature detection with semantic dataflow tracking and threat modeling.   

OWASP Top 10 and CWE Top 25: These models provide a taxonomy of critical security weaknesses, such as injection attacks, broken access controls, and cryptographic failures.   

OWASP Application Security Verification Standard (ASVS) v5.0.0: The ASVS provides a testable framework of web application security controls. Level 1 controls can be checked automatically using static tools or dynamic analysis. Level 2 (Standard) and Level 3 (Advanced) controls focus on sensitive data transactions and require hybrid code reviews and detailed threat modeling.   

NIST Secure Software Development Framework (SSDF) SP 800-218: The SSDF defines secure development practices across the software lifecycle, focusing on build environment protection, tamper-resistant deployment pipelines, and automated evidence collection.   

Supply-chain Levels for Software Artifacts (SLSA) v1.1: SLSA provides guidelines for securing software builds and dependencies. The Build track ensures artifact integrity, preventing tampering from source commit to binary distribution.   

Secrets Management: This standard enforces the complete elimination of hardcoded API keys, private keys, and tokens from both active workspace files and historical git commit logs.   

Code Quality and Maintainability
Structural quality is assessed using standardized metrics and object-oriented design principles:

ISO/IEC 25010:2023: This international standard defines a software product quality model. Maintainability is evaluated across sub-characteristics like modularity, reusability, analyzability, modifiability, and testability.   

SOLID Design Principles: These principles help ensure object-oriented codebases remain modular, extensible, and easy to maintain over time.

Structural Metrics: Cyclomatic complexity measures the number of linearly independent paths through a program's source code, while the Maintainability Index uses a weighted formula to calculate an overall quality score from 0 to 100.

Google Engineering Practice Guides: These guides serve as standard baselines for code clarity, size optimization, naming conventions, and documentation completeness.

Testing and Robustness
Test suites must be verified for semantic verification capability rather than simple statement execution:   

Code Coverage Types: Statement, branch, and path coverage measure which lines are executed by test runners, though they do not guarantee that assertions actually validate program behavior.   

Test Pyramid: This guideline balances testing effort by advocating for a high volume of isolated unit tests, a moderate volume of integration tests, and a minimal set of end-to-end (E2E) tests.

Mutation Testing: This approach injects synthetic faults (mutants) into the source code to verify whether the test suite detects and fails on the bug. The mutation score represents the percentage of mutants successfully "killed".   

Accessibility, Licensing, and Documentation
Web Content Accessibility Guidelines (WCAG 2.2) and Section 508: These standards verify keyboard focus navigation, ARIA attributes, semantic HTML markup, and color contrast ratios.   

Licensing and Compliance: This involves auditing open-source dependencies to prevent licensing conflicts, such as viral GPL licenses in commercial proprietary applications.

Documentation Completeness: This verifies that public APIs, setup workflows, and environment variables are documented in resources like README.md or OpenAPI schemas.

Mathematical Verification and Quality Modeling
Evaluating software reliability and security requires formal mathematical models. To verify that an LLM-based audit remains grounded, one can use Surprise Adequacy (DSA 
0
​
 ) to calculate the novelty of input test cases against the training distribution. Given hidden activation traces Φ(x) and a test input x 
t
​
  of true class y 
t
​
 , DSA 
0
​
  is defined as:   

DSA 
0
​
 (x 
t
​
 )= 
∥Φ(x 
a
​
 )−Φ(x 
b
​
 )∥ 
2
​
 
∥Φ(x 
t
​
 )−Φ(x 
a
​
 )∥ 
2
​
 
​
 
where x 
a
​
  represents the nearest training data point of class y 
t
​
 , and x 
b
​
  represents the nearest training point of a different class. This metric helps ensure that the inputs analyzed by auditing agents fall within predictable reasoning boundaries.   

To compile a project's overall quality score based on the ISO/IEC 25010 standard, the system calculates an aggregated value Q 
i
​
  for each quality characteristic:   

Q 
i
​
 = 
j
∑
​
 w 
ij
​
 m 
ij
​
 
where m 
ij
​
  represents the value of the j-th metric for the i-th characteristic, and w 
ij
​
  represents its assigned weight, determined through expert consensus or analytic hierarchy processes.   

To distinguish between automatable rules and tasks requiring contextual AI judgment, the following table maps standard requirements to their appropriate verification methods:   

Domain	Assessment Criterion	Machine-Checkable Indicators	Requires LLM Judgment
Security

[cite: 9, 23]

SQLi, XSS, Secret Exposure, and Auth Controls

Regex secret matches, static AST query patterns, and direct CVE dependency lookups.

Assessing access-control boundaries across multi-tenant API scopes.

Supply Chain

[cite: 14, 17]

SLSA Build Integrity & NIST SSDF

Checking branch protection states and verifying lockfile checksums.

Verifying the intent of package additions and reviewing pipeline configurations.
Quality

[cite: 25]

SOLID, Complexity, and Code Smells

Calculating Cyclomatic Complexity, line lengths, and duplicate code blocks.

Assessing Single Responsibility violations and naming clarity.

Testing

[cite: 27, 28]

Coverage Validation & Mutation Testing

Generating coverage percentages and running Stryker/mutmut mutations.

Assessing if test assertions are semantically meaningful or merely executing code.

Accessibility

[cite: 31]

Keyboard Focus & Contrast Ratios

Running Axe CLI to detect missing alt-text or duplicate DOM elements.

Assessing keyboard trap logic in complex modal dialogs.

Compliance

[cite: 40]

Manifest Licenses & Documentation

Parsing license terms in package manifests and verifying file paths.

Evaluating documentation clarity and accuracy relative to system behavior.

  
2. Deterministic Tooling as Ground-Truth Signal
Relying solely on LLMs to perform zero-shot code auditing yields high hallucination rates and misses deep dataflow vulnerabilities. High-performance auditing agents integrate deterministic static analysis security testing (SAST), software composition analysis (SCA), and linting tools to establish a high-recall baseline, leveraging the LLM as a precision-oriented triage and remediation layer.   

Ecosystem Tooling Review
The worker agents should have access to a suite of command-line tools across various development ecosystems:

Semgrep (Open-Core): An AST-based pattern matcher that parses code into generic trees, searching for patterns using a syntax-aware query language. It is highly extensible and runs in seconds, making it ideal for rapid pull-request (PR) reviews.   

CodeQL (Closed-Core / Free for Open-Source): GitHub’s whole-program semantic analysis engine. It compiles codebases into relational databases and executes queries to track untrusted inputs across complex, multi-step execution paths. It offers higher precision than pattern matchers but requires significant compilation time and memory.   

SonarQube / SonarLint (Open-Core): Industry standards for code quality and maintainability. They track code smells, duplications, and cognitive complexity, outputting quality grades.   

Bandit (Open-Source): A Python-focused SAST tool that scans AST nodes for common security issues, such as hardcoded passwords or insecure subprocess invocations.   

ESLint (Open-Source): The standard AST-based linter for JavaScript and TypeScript, checking for syntax errors and style guide violations.   

Ruff (Open-Source): An extremely fast Rust-based linter and formatter for Python, replacing Flake8, Black, and Bandit while outputting standardized JSON diagnostics.   

Snyk Code / Snyk Container (Commercial): Enterprise developer security platforms that scan custom code, open-source dependencies (SCA), container bases, and infrastructure-as-code (IaC) files.   

Trivy (Open-Source): A comprehensive security scanner that detects vulnerabilities, misconfigurations, and hardcoded secrets in filesystems, container images, and git repositories.   

Gitleaks (Open-Source): A specialized, high-performance secret scanner that audits git history and active files using entropy and regex signatures, preventing token leaks prior to commit.   

Dependabot & OWASP Dependency-Check (Open-Source): SCA tools that parse package manifests to identify libraries with known CVEs and suggest version upgrades.

Integrating Deterministic Scanners with LLM Triage
Deterministic tools excel at structural coverage but struggle with high false-positive rates, often flagging non-exploitable paths or intentional mock implementations. For example, the OWASP Benchmark v1.2 reveals that CodeQL and Semgrep have false-positive rates of 68.2% and 74.8%, respectively.   

A hybrid system addresses this by configuring local scanners to output findings in standardized JSON or SARIF formats. A downstream LLM agent parses these findings alongside the surrounding source code context to evaluate exploitability and relevance. A study on OWASP Benchmark false-positive mitigation demonstrated that applying an LLM-based post-filtering layer to static analysis reports reduced initial false-positive rates from over 92% to 6.3%.   

To implement this, the orchestrator executes local tools inside isolated, ephemeral containers (such as jailkits or microVMs) to parse files safely. The resulting diagnostics are structured using standardized CLI flags:   

Bash
# Gitleaks: Scan repository history and output JSON
gitleaks detect --source=. --report-format=json --report-path=gitleaks-report.json

# Trivy: Scan local filesystem for vulnerabilities and secrets
trivy fs --format json --output trivy-report.json .

# Ruff: Execute security and error checks on Python files
ruff check --select S,B --format json --output ruff-report.json .

# Bandit: Scan Python AST structures for common vulnerabilities
bandit -r . -f json -o bandit-report.json

# Semgrep: Run security rules and output findings in JSON format
semgrep scan --config=auto --json --output=semgrep-report.json
3. Analysis of Prior Art and Empirical Baselines
Automated code review, vulnerability detection, and program repair have evolved from basic regex checks to multi-agent architectures that build semantic codebase graphs.   

Existing Commercial and Open-Source Systems
CodeRabbit: A leading commercial AI code-review platform. It clones repositories into ephemeral, sandboxed VM containers and runs over 40 linters and SAST tools in parallel. Instead of relying on similarity-based vector database retrieval, CodeRabbit builds a structural AST code graph of the codebase. This graph maps dependencies, tracking how changes in one module impact downstream call sites. Downstream judge models validate findings against Jira/Linear tickets and CI logs before posting suggestions to the PR.   

PR-Agent (CodiumAI / Qodo): An open-source, highly customizable PR review agent. It runs inside GitHub Actions or local containers, producing automated descriptions, code quality analyses, and inline suggestions.   

Greptile: An AI code analysis system that constructs a semantic dependency graph of the codebase. It excels at architectural-level reviews, tracing dataflow and structural dependencies across multi-file pull requests.   

Sourcery: A Python-centric automated refactoring tool that integrates directly into IDEs and PR pipelines, suggesting idiomatic code improvements with clear before-and-after diffs.   

Codacy: A static analysis platform that aggregates structural linter findings and tracks overall codebase health metrics, assigning a quality grade (A–F) to projects over time.   

Amazon CodeGuru: A cloud-based static analysis and security scanning tool that integrates machine learning to flag concurrency bugs, resource leaks, and performance bottlenecks.   

s0-cli: An open-source, hybrid CLI scanning tool that runs traditional scanners (Semgrep, Bandit, Ruff, Gitleaks, Trivy) and uses a multi-turn LLM agent to triage findings and explain vulnerabilities. It includes a self-optimizing "Meta-Harness" outer loop that automatically rewrites prompts based on historical run performance.   

Academic Frameworks and Methodology Insights
Academic research focuses on formalizing multi-agent cooperation, mathematical validation, and testing frameworks:

MultiVer (Zero-Shot Ensemble): An academic multi-agent vulnerability detection system that runs a four-agent ensemble (Security, Correctness, Performance, and Style) with a union-voting mechanism. MultiVer demonstrates that a zero-shot multi-agent ensemble can achieve 82.7% recall on the PyVul benchmark, outperforming fine-tuned single-model systems. It uses a three-tier pipeline: pattern matching, FAISS-based vector retrieval of similar CWEs, and extended-thinking LLM runs.   

CodeX-Verify (Information-Theoretic Multi-Agent Framework): CodeX-Verify mathematically proves that combining agents with distinct analysis patterns detects more bugs than single-agent setups. It establishes that agent consensus is most effective when individual agent correlations are low (ρ=0.05−0.25). Additionally, it introduces a multiplicative model for compound vulnerabilities, formalizing how chained exploits exponentially increase risk.   

SecVulEval (Statement-Level C/C++ Evaluation): A high-fidelity benchmark tracking 25,440 functions to evaluate statement-level security reasoning. It highlights that model performance drops significantly when tracing complex variable states, demonstrating the need for rich, cross-procedural context engines.   

3+1 Heterogeneous Multi-Agent Architecture: This design combines three cloud-based expert agents (focused on structure, security, and edge-case logic) with a lightweight, local verifier model (e.g., Qwen3-8B). The local verifier reviews the experts' outputs to identify hallucinations, inconsistencies, or missed vulnerabilities at zero marginal API cost.   

VulnSage (Automated Exploit Generation): Inspired by human security workflows, VulnSage decomposes vulnerability verification into specialized sub-agents (Code Analyzer, Code Generator, Validation, and Reflection). It uses automated exploit generation to confirm the validity and impact of flagged vulnerabilities.   

MAVUL (Interactive Multi-Agent System): This system coordinates a Vulnerability Analyst agent (which traces cross-procedural dataflows) and a Security Architect agent (which provides iterative feedback over multiple conversation rounds) to refine detection accuracy.   

The following table compares these platforms and academic architectures to identify proven design patterns:

Tool / Paper	Approach	Status	Key Strengths	Core Weaknesses	Elements to Borrow
CodeRabbit

[cite: 49]

AST-based code graphs + deterministic linters + LLM judge.

Commercial	
Low noise, deep context modeling, learns from developer feedback.

High compute cost, closed-source context graph engine.

AST-based dependency graph compilation and downstream LLM triage.

PR-Agent

[cite: 37]

Highly configurable prompt pipelines in CI/CD.

Open-Source	
Highly customizable, self-hostable, multi-platform integrations.

Primarily file-diff based, misses broad architectural regressions.	
Custom prompt overrides and template-driven output generation.

s0-cli

[cite: 2]

Deterministic linter execution + LLM-based triage.

Open-Source	
Runs locally, zero-cost raw modes, meta-harness auto-optimization.

Lacks structural AST call-graph tracing, limited to standard linters.	
Standardized CLI-to-JSON parser and self-optimizing prompt harness loops.

MultiVer

[cite: 7]

Three-tier pipeline: static rules, vector RAG, Opus 4.5 reasoning.

Academic	
82.7% recall on PyVul, bypasses fine-tuning needs.

Low precision (48.8%), high latency from extended thinking runs.

Three-tier progressive disclosure pipeline and union-voting.

CodeX-Verify

[cite: 1]

4 parallel agents (correctness, security, perf, style).

Academic	
High accuracy improvement (+39.7pp) via low-correlation agents.

Requires parallel API calls, increasing token cost.

Mathematically proven low-correlation specialist agent classification.

3+1 Architecture

[cite: 5]

3 parallel cloud experts + 1 local verifier model

Academic	
Reaches 100% recall on Juliet Suite, extremely low execution cost.

High local hardware requirements to run local verifiers.	
Local-cloud division where a cheaper model acts as an adversarial judge.

  
4. Multi-Agent Orchestration and Design Patterns
Designing an enterprise code-auditing skill requires structuring the system with specialized, low-correlation worker agents managed by a centralized, high-reasoning orchestrator. This design isolates context, limits token bloat, and reduces false positives.   

                     ┌────────────────────────────────┐
                     │    Manager/Orchestrator Agent  │
                     │      (High-Reasoning Model)    │
                     └───────────────┬────────────────┘
                                     │
           ┌─────────────────────────┼─────────────────────────┐
           ▼                         ▼                         ▼
┌────────────────────┐    ┌────────────────────┐    ┌────────────────────┐
│  Security Expert   │    │ Correctness Expert │    │ Performance Expert │
│  (CWE/ASVS Analyst)│    │   (Logic Auditor)  │    │ (Complexity Agent) │
└──────────┬─────────┘    └──────────┬─────────┘    └──────────┬─────────┘
           │                         │                         │
           └─────────────────────────┼─────────────────────────┘
                                     ▼
                     ┌────────────────────────────────┐
                     │   Lightweight Adversarial      │
                     │    Verifier / Judge Agent      │
                     └───────────────┬────────────────┘
                                     ▼
                      [Consolidated Audit Report]
Orchestration Workflows
Anthropic's research on agent architectures defines five core workflow patterns:   

Sequential Processing (Chains): Breaks tasks into linear steps, passing output from one step as input to the next. For audits, this is structured as:
  

Repository Scan⟶Taint-Flow Mapping⟶Exploit Validation⟶Report
Parallelization (Fan-Out / Fan-In): Spawns independent workers to analyze the codebase simultaneously, aggregating results programmatically. This pattern is ideal for running specialized inspectors in parallel, minimizing overall latency.   

Routing: Uses a classifier agent to evaluate the codebase characteristics first, routing tasks to specialized experts (e.g., directing a React codebase to a web security agent and an internal C++ library to a memory safety agent).   

Orchestrator-Workers: A central manager plans the audit, delegates sub-tasks to workers, and compiles their findings. This pattern is ideal for multi-file codebases with unpredictable execution branches.   

Evaluator-Optimizer: An iterative loop where a worker proposes solutions (such as security patches) and an evaluator reviews them. The worker iterates until the evaluator approves the patch.   

Validation, Deduplication, and Conflict Resolution
To maintain a high signal-to-noise ratio, the manager must use structured validation and conflict-resolution routines:   

Adversarial Cross-Checking: Following the "3+1" model, a separate verification agent reviews all worker findings, filtering out hallucinations and checking for logical consistency.   

Consolidated Schema: Findings should use a typed structure to ensure programmatic predictability:

Finding=⟨ScannerID,CWE,File,Line,Severity,Confidence,Evidence,FixDiff⟩
Deduplication Matrix: If the security agent and the correctness agent flag the same code block, the orchestrator merges the duplicate findings. It recalculates severity using a compound risk formula, elevating the priority if a bug presents multiple compounding vulnerabilities.   

Conflict Resolution: If a static tool flags an issue but the LLM expert deems it non-exploitable, the orchestrator acts as a judge. It can run simulated execution or trace the call path to make a final decision.   

Context Window and Token Cost Trade-offs
Dividing tasks among multiple specialized agents provides significant structural advantages over single-agent systems, though it requires careful resource management:   

Context Isolation: Spawning separate workers with specialized system prompts reduces context window consumption per call, preventing "context collapse" where models miss granular details in long threads.   

Computational Overhead: Multi-agent setups increase token consumption, often using up to seven times more tokens than single-thread sessions.   

Optimization Strategies: To optimize costs, developers should use cheaper, faster models (e.g., Claude Haiku) for read-only codebase exploration and reserve high-reasoning models (e.g., Claude Sonnet or Opus) for structural analysis and orchestrator operations.   

Mathematical Verification and Compounding Vulnerabilities
In code verification, the mathematical foundation of agent consensus assumes that multiple specialized workers with distinct analysis profiles yield a higher cumulative detection rate than any single general-purpose agent. Using mutual information I to represent the knowledge gained about software bugs B, this relationship is expressed as:   

I(A 
1
​
 ,A 
2
​
 ,A 
3
​
 ,A 
4
​
 ;B)> 
i
max
​
 I(A 
i
​
 ;B)
This inequality holds when the worker agents are designed to look for different, non-overlapping categories of bugs.   

Additionally, the risk of compounding vulnerabilities within the same repository must be modeled. Traditional security assessments sum risks linearly, but chained vulnerabilities (such as a SQL injection coupled with exposed administrative credentials) can create exponentially higher impact. This compounding risk is formalized as:   

Risk(v 
1
​
 ∪v 
2
​
 )=Risk(v 
1
​
 )×Risk(v 
2
​
 )×α(v 
1
​
 ,v 
2
​
 )
where Risk(v 
1
​
 ) and Risk(v 
2
​
 ) represent the individual risk values, and α(v 
1
​
 ,v 
2
​
 ) is a compounding factor (e.g., α∈{1.5,2.0,2.5,3.0}) that scales based on how easily the vulnerabilities can be chained together by an attacker.   

5. Claude Code Skill and Subagent Implementation Specifics
Claude Code provides a robust extensibility model that enables developers to author custom slash commands, project-wide instructions (memory), and specialized sub-agents.   

Core Customization Mechanisms
Claude Code supports three primary extension mechanisms:   

CLAUDE.md (Persistent Memory): Markdown files located at the root of a project or nested within subdirectories. They are automatically loaded into Claude's context at the start of each session, making them ideal for project-wide styling guides, build commands, and architectural standards.   

Skills (SKILL.md): A standardized format for packaging reusable capabilities, containing YAML metadata and markdown instructions in a SKILL.md file. Skills are discoverable and can be invoked explicitly via slash commands (e.g., /my-skill) or triggered opportunistically by Claude.   

Subagents (.claude/agents/): Autonomous, task-specific worker agents that execute inside their own context windows. They inherit the parent conversation's permissions but can be restricted to specific toolsets (e.g., read-only access), keeping the main chat thread clean.   

Authoring Project-Level Sub-Agents
To deploy project-specific sub-agents, files must be stored in the .claude/agents/ directory. The following configuration illustrates a security auditor sub-agent, configured in .claude/agents/security-auditor.md:   

YAML
---
name: security-auditor
description: An expert security auditing sub-agent that scans files for OWASP Top 10 vulnerabilities, secrets, and supply-chain weaknesses.
tools: Read, Grep, Glob
disallowedTools: Write, Edit, Bash
model: sonnet
permissionMode: default
effort: high
memory: project
background: false
---

You are a Senior Application Security Auditor. Your sole task is to analyze files within this repository for security risks.
Focus on identifying:
1. OWASP Top 10 vulnerabilities, especially SQL injection and broken access control.
2. Hardcoded API keys, tokens, or credentials.
3. Supply-chain vulnerabilities in configuration files and lockfiles.

You operate under the principle of least privilege. You have read-only access to the filesystem.
Provide findings in a clear markdown format, detailing the file path, line numbers, description of the vulnerability, and its potential impact.
The "Task" Tool and Sub-Agent Spawning
The orchestrator agent can programmatically spawn sub-agents using the built-in Task tool. It can also use the context: fork command modifier to run memory-intensive, multi-file scans in a separate sub-agent, keeping the main thread clean.   

Custom Slash Command: .claude/skills/audit/SKILL.md
name: audit
description: Run a multi-agent code quality, correctness, and security audit.
allowed-tools: Read, Glob, Grep, Task, Skill
Execute a multi-agent audit by following these steps:

Use the Task tool to spawn the "security-auditor" sub-agent in parallel to analyze the codebase for vulnerabilities.

Use the Task tool to spawn the "correctness-auditor" sub-agent in parallel to analyze the codebase for logic errors.

Consolidate the returned summaries and ask the user for confirmation before proposing fixes.

$ARGUMENTS

Portability and Tool Restrictions
Agent Skills Open Standard: The SKILL.md format is an open standard developed by Anthropic. It is portable across multiple AI coding platforms, including OpenAI Codex, Cursor, GitHub Copilot, and Gemini CLI.   

Ecosystem Mappings: While Claude Code uses frontmatter fields like allowed-tools or permissionMode to manage execution, other systems map these settings to distinct files:   

Platform	Specification File	Custom Command Location	Platform-Specific Metadata
Claude Code

[cite: 3, 59]

SKILL.md

[cite: 59]

.claude/skills/

[cite: 59]

permissionMode, effort

[cite: 38]

GitHub Copilot

[cite: 65]

SKILL.md

[cite: 65]

.github/skills/

[cite: 65]

VS Code customization options

OpenAI Codex

[cite: 4]

SKILL.md

[cite: 4]

.codex/skills/	
openai.yaml metadata

  
Tool Restrictions and Enforcement: Tool access is governed by the permissionMode and tools fields. However, there is a known bug in Claude Code CLI where allowed-tools restrictions declared in a skill's YAML frontmatter are not strictly enforced, occasionally allowing Claude to access tools outside the specified list. System prompts must explicitly state tool restrictions to reinforce these boundaries.   

6. Report Synthesis and Human-in-the-Loop Workflows
Presenting audit findings clearly is essential for helping developers understand security risks and act on them safely.   

Risk Formulation
Vulnerability prioritization is modeled dynamically to ensure critical, exposed flaws are addressed first:   

Risk=CVSS×EPSS×EnvironmentalFactor
CVSS (Severity): Calculates the technical severity of vulnerabilities using Base, Temporal, and Environmental metrics. Base metrics evaluate exploitability characteristics (Attack Vector, Complexity, Privileges, User Interaction) and potential impact (Confidentiality, Integrity, Availability).   

EPSS (Likelihood): Exploit Prediction Scoring System probabilities indicate the likelihood that a vulnerability will be actively exploited in the wild.   

VPR (Environmental Exposure): Vulnerability Priority Rating scales technical severity based on the asset's environmental exposure, prioritizing public-facing systems over isolated test workloads.   

Proposed Fixes and Safe Staged Workflows
AI-driven repairs must use a human-in-the-loop workflow to prevent accidental modifications or build regressions:   

Unified Diffs: The agent presents the unified diff and explains the associated risk.   

Explicit User Confirmation: The agent requests user authorization before writing to the filesystem.   

Automated Verification: The agent applies modifications locally and runs verification tests to confirm the fix works.   

Automated Rollback: If tests fail, the agent uses checkpointing or runs /rewind to safely revert the workspace to its clean git state.   

Recommended Inspector-Agent Mapping
The following table outlines the recommended sub-agent mapping, linking each specialized worker to its objective standards, targets, and toolchains:

Inspector Sub-Agent	Standard / Rubric	Target Scope	Local Toolchain	Machine-Checkable Indicators	Requires LLM Judgment
Security Expert	
OWASP Top 10, CWE Top 25

SQLi, XSS, SSRF, broken auth.

Semgrep, CodeQL, Gitleaks, Bandit.

Hardcoded secrets, clear static vulnerabilities, and known bad patterns.

Verifying multi-tenant auth and data boundary logic.

Quality & Maintainability	
ISO/IEC 25010, SOLID

Code smells, complexity, and duplicate code.

ESLint, Ruff, SonarLint.

Cyclomatic complexity and duplicate code percentages.

Assessing SOLID design violations and naming clarity.

Logic & Correctness	
IEEE Standard 1044

Race conditions, off-by-one errors, and exception handling.

Compiler, runtime logs, and test runners.

Direct syntax errors and failing test cases.

Tracing variable state changes across complex logic.

Performance & Resource	
ISO/IEC 25010 Performance

Resource leaks, algorithmic complexity, and db locks.

Language profilers and database query loggers.	Open file handles, blocking calls, and N+1 query patterns.	Identifying algorithmic efficiency gaps.
Testing & Robustness	
Test Pyramid, Mutation Score

Coverage gaps, assertion strength, and edge-case validation.

Stryker, mutmut, pytest-cov.

Statement and branch coverage percentages.

Verifying that assertions validate code behavior.

Supply Chain & License	
SLSA v1.1, NIST SSDF

Third-party dependencies, open-source licenses, and build security.

Trivy, OSV-Scanner, scorecards.

Known dependency CVEs and license compliance.

Assessing the risk of third-party architecture patterns.
Accessibility & Docs	
WCAG 2.2, Section 508

Keyboard traps, ARIA focus, alt text, and public API docs.

Axe CLI, markdown-lint, OpenAPI.

Missing alt text, broken links, and duplicate DOM elements.

Assessing manual accessibility workflows.

  
Orchestration Architecture Configurations
The following table outlines three candidate architectures for coordinating these worker agents, highlighting their technical trade-offs:

Configuration Pattern	Orchestration Mechanism	Token Efficiency	Structural Resilience	Best Suited For	Key Trade-off
Parallel Fan-Out / Fan-In

[cite: 54]

Spawns all specialized worker agents concurrently. A centralized orchestrator aggregates their JSON reports.

Low token efficiency; runs parallel worker calls that consume higher overall tokens.

High resilience; individual worker failures do not crash the audit run.	
Rapid workspace scans and pull-request verification.

Higher peak token consumption and model rate limit usage.

Evaluator-Optimizer Chain

[cite: 54]

A worker proposes remediation code, and an adversarial judge reviews it for regressions.

Moderate token efficiency; requires iterative, sequential LLM calls.

High resilience; ensures generated changes are validated.

Applying deep bug repairs to complex legacy files.

Higher execution latency due to sequential worker runs.

Router-Led Specialist Execution

[cite: 54]

A router evaluates the codebase language and triggers only the relevant specialist sub-agents.

High token efficiency; limits active workers to reduce token usage.

Low resilience; router errors can result in missed audits.	
Large-scale, multi-language monorepos.

Highly dependent on the router's ability to accurately assign tasks.

  
