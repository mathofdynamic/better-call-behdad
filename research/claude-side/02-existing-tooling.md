# 02 — Existing Tooling to Wrap or Learn From

> Research brief for **Better-call-behdad** — a multi-agent code-audit skill.
> Goal: catalog the deterministic static-analysis / SAST / SCA / secrets / quality tooling an AI agent can invoke as **ground-truth signal**, then describe how to combine those tools with LLM reasoning.
> Date: 2026-07-01. Sources at the bottom.

---

## 0. TL;DR for the skill designer

- **Don't reinvent detection.** Mature, headless-friendly, JSON/SARIF-emitting tools already exist for every major ecosystem. The agent's value-add is *orchestration, triage, cross-tool correlation, and explanation* — not re-deriving taint analysis in a prompt.
- **Standardize on SARIF where possible.** SARIF (OASIS standard, JSON-based) is the lingua franca: Semgrep, CodeQL, ESLint, Bandit, Trivy, Gitleaks, Snyk, OWASP Dependency-Check, Grype, OSV-Scanner all emit it. One parser → N tools. Fall back to each tool's native JSON when SARIF is lossy.
- **Split the problem into 4 signal classes** and pick a default tool per class:
  1. **SAST / code patterns** → Semgrep (breadth), CodeQL (depth), plus language-native linters (Ruff/Bandit, ESLint).
  2. **SCA / dependency CVEs** → OSV-Scanner or Trivy (free) / Snyk (commercial); Dependabot/Renovate for *remediation PRs*.
  3. **Secrets** → Gitleaks.
  4. **IaC / containers / misconfig** → Trivy, Checkov, Grype+Syft.
- **The winning pattern is hybrid:** run deterministic tools to bound the search space (high recall, ground-truth locations + rule IDs + CWEs), then use the LLM to triage false positives, add data-flow narrative, dedupe across tools, and prioritize. Recent research (SAST-Genius, ZeroFalse, AdaTaint) shows ~90% FP reduction and ~30% faster triage from exactly this arrangement.

---

## 1. SAST & code-pattern tools

### Semgrep (Community Edition)
- **Checks:** Pattern-based static analysis — security bugs, anti-patterns, secure-coding guardrails, custom org rules. Bug-variant matching via patterns that "look like source code."
- **Languages:** 30+ — Apex, Bash, C, C++, C#, Clojure, Dart, Dockerfile, Elixir, Go, Java, JS/TS/JSX/TSX, JSON, Kotlin, Lua, OCaml, PHP, Python, R, Ruby, Rust, Scala, Solidity, Swift, Terraform, YAML, and a "generic" mode (ERB, Jinja).
- **License:** Open source (LGPL-ish core); Semgrep Pro/AppSec is commercial (adds cross-file/interfile dataflow, more rules). OpenGrep is a community fork.
- **CLI / headless:** Yes, first-class. `semgrep scan --config auto` or a ruleset path; fully non-interactive.
- **Output:** `--json`, `--sarif` (and `--sarif-output FILE`), plus text/GitLab formats. JSON carries file paths, line/col spans, severity, autofix suggestions.
- **Agent wrapping:** Ideal default SAST engine. Run with a curated ruleset (or `p/ci`), parse SARIF, group by `ruleId`+`fingerprint`. Agent can also *author custom Semgrep rules on the fly* (YAML) for project-specific patterns, which is a strong differentiator.

### CodeQL (GitHub)
- **Checks:** Semantic, dataflow/taint-based analysis via queries over a compiled code database. Deepest detection for injection, deserialization, path traversal, etc.
- **Languages:** C/C++, C#, Go, Java, Kotlin, Swift, Rust (compiled) + JS/TS, Python, Ruby (non-compiled). Requires building a DB first (`codeql database create`), then `codeql database analyze`.
- **License:** CLI is free; queries are open source. **License restriction:** free only for open-source / research / academic use — commercial closed-source use of the CLI historically requires GitHub Advanced Security. Check current terms before shipping.
- **CLI / headless:** Yes, but heavier: DB build step, longer runtime, needs a working build for compiled langs.
- **Output:** SARIF (`--format=sarifv2.1.0`), CSV. Rich flow-path steps in SARIF (source→sink), which are gold for LLM narration.
- **Agent wrapping:** Use as the "deep pass" on hotspots Semgrep flags, or on a schedule. Two-phase (create DB, analyze) means the agent must manage build environments. Best value: feed CodeQL's dataflow paths to the LLM for explanation.

### SonarQube / SonarQube for IDE (formerly SonarLint) / SonarScanner CLI
- **Checks:** Code quality + reliability + security (bugs, code smells, security hotspots, duplications, coverage gating). Strong **Quality Gates** (pass/fail thresholds on new code).
- **Languages:** 40+ commercial; **Community Build covers 20+** (Java, JS/TS, Python, C#, PHP, Go, Ruby, Kotlin, etc.).
- **License:** Community Build is open source/self-hosted. Branch analysis + PR decoration are commercial-only (a real limitation for PR workflows). SonarQube Cloud is SaaS.
- **CLI / headless:** SonarScanner CLI runs build-system-agnostic; but it **posts results to a server** rather than printing a self-contained report — more infra than a one-shot linter.
- **Output:** Results live on the server/API; quality-gate status queryable via API. Less "pipe-to-stdout JSON" friendly than the others.
- **Agent wrapping:** Best when a Sonar server already exists — agent reads the Web API for issues + gate status. Heavier to stand up from scratch; SonarQube-for-IDE is for humans in-editor, not headless agents.

### Bandit (PyCQA)
- **Checks:** Python-only security SAST via AST — hardcoded passwords, `eval`/`exec`, weak crypto, `subprocess`/shell injection, insecure deserialization. Reports severity + confidence.
- **Languages:** Python only.
- **License:** Open source (PyCQA).
- **CLI / headless:** Yes. `bandit -r ./ -f json -o out.json`.
- **Output:** screen, **JSON**, **SARIF**, HTML, XML, YAML, CSV. Supports baselines for diffing builds.
- **Agent wrapping:** Cheap, fast Python security pass. Pair with Ruff (style/bugs) + Semgrep (broader). Severity+confidence fields help the LLM prioritize.

### Ruff (Astral)
- **Checks:** Extremely fast Python linter + formatter (Rust). 900+ rules re-implementing Flake8, isort, pyupgrade, pydocstyle, flake8-bugbear, some Bandit (`S`) rules, etc. Not a security tool per se but catches correctness/bug-prone patterns.
- **Languages:** Python.
- **License:** Open source (MIT).
- **CLI / headless:** Yes, sub-second on large repos (10–100× Flake8/pylint). `ruff check --output-format json`.
- **Output:** JSON, SARIF, text, GitHub/GitLab; `--statistics`; `--fix` for autofix.
- **Agent wrapping:** Run first as a fast, broad "is this even clean?" gate. `--select` to scope rule families; JSON is trivial to parse. Autofix lets the agent propose diffs.

### ESLint
- **Checks:** JS/TS static analysis — correctness, style, many security/quality plugins (e.g. `eslint-plugin-security`, `@typescript-eslint`). Pluggable rule engine.
- **Languages:** JavaScript, TypeScript (via `@typescript-eslint`), JSX/TSX; flat config (`eslint.config.js`).
- **License:** Open source (MIT).
- **CLI / headless:** Yes. `eslint . -f json`. SARIF via `@microsoft/eslint-formatter-sarif`.
- **Output:** JSON (built-in), SARIF (formatter package), many others via `--format`.
- **Agent wrapping:** The JS/TS analog of Ruff+Bandit. Agent must respect the project's existing config/plugins. Good for correctness signal; layer Semgrep for deeper security.

---

## 2. SCA — dependency / supply-chain vulnerability tools

### OSV-Scanner (Google)
- **Checks:** Known-vuln (CVE/advisory) scanning of dependencies via the OSV.dev database; official frontend to OSV + OSV-Scalibr. V2 adds source-code reachability-ish and container layer-aware scanning.
- **Languages/ecosystems:** 11+ languages, 19+ lockfile types — npm, PyPI/pip, Maven, Gradle, Go modules, Cargo, RubyGems, Composer, NuGet, and more; SPDX + CycloneDX SBOM input.
- **License:** Open source (Apache 2.0), free.
- **CLI / headless:** Yes. `osv-scanner --lockfile=... --format=sarif`. Multiple lockfiles at once.
- **Output:** JSON, SARIF, HTML, table.
- **Agent wrapping:** Strong free default for SCA. Point at lockfiles or an SBOM; correlate CVE IDs with severity. Authoritative, open advisory source (good for LLM to cite).

### Trivy (Aqua Security)
- **Checks:** All-in-one — dependency CVEs (`fs`), container image vulns, IaC/misconfig (`config`: Terraform, K8s, Dockerfile), **secrets**, license, SBOM generation. ~31k★.
- **Languages/ecosystems:** Broad OS package + language ecosystems + IaC formats + container images + K8s clusters.
- **License:** Open source (Apache 2.0), free.
- **CLI / headless:** Yes, very. `trivy fs --format sarif -o out.sarif .`; `-f/--format`, `-o/--output`.
- **Output:** table, **JSON**, **SARIF**, CycloneDX, SPDX, JUnit. SARIF feeds GitHub Code Scanning / AWS Security Hub.
- **Agent wrapping:** The "one binary, many signal classes" option — good when you want SCA + IaC + secrets + containers from a single tool with uniform output. Great low-friction default.

### Snyk (commercial, has free tier + CLI)
- **Checks:** Snyk Open Source (SCA), Snyk Code (SAST), Snyk Container, Snyk IaC. Reachability, fix advice, proprietary vuln DB.
- **Languages/ecosystems:** SCA across npm, PyPI, Maven, Gradle, NuGet, Go, RubyGems, Composer, CocoaPods, Cargo, SwiftPM, Hex, etc. SAST is a narrower language set.
- **License:** Commercial (free tier with limited tests/month); CLI free to install.
- **CLI / headless:** Yes. `snyk test --json`, `snyk code test --sarif-file-output=...`. Note quirks: SCA writes a JSON file even with no issues; Code writes none if clean; multiple scans to the same `--sarif-file-output` overwrite each other.
- **Output:** JSON, SARIF.
- **Agent wrapping:** Use when an org already has Snyk (auth token). Watch the SARIF-overwrite gotcha — write per-scan files. Otherwise prefer OSV-Scanner/Trivy to avoid auth + quota.

### OWASP Dependency-Check
- **Checks:** SCA against the NVD (CPE→CVE matching); augmented by NPM Audit API, OSS Index, RetireJS, Bundler-Audit.
- **Languages/ecosystems:** Java (Maven/Gradle), .NET (NuGet), JS (npm), Python (pip), Ruby (Bundler), Go.
- **License:** Open source (OWASP).
- **CLI / headless:** Yes, but first-run NVD data download is slow (needs an NVD API key now). `--format SARIF` (also HTML/XML/CSV/JSON/JUnit/GitLab/ALL).
- **Output:** HTML, XML, CSV, JSON, SARIF, JUnit.
- **Agent wrapping:** Solid for JVM/.NET shops; heavier setup (NVD sync). OSV-Scanner/Trivy are lighter-weight for most agents.

### Grype + Syft (Anchore)
- **Checks:** Syft generates an SBOM (packages/deps); Grype scans images/filesystems/SBOMs for known vulns.
- **Languages/ecosystems:** Major OS package managers + language deps; works from Syft SBOMs.
- **License:** Open source (Apache 2.0).
- **CLI / headless:** Yes. `syft <img> -o cyclonedx-json`; `grype sbom:./sbom.json -o sarif`.
- **Output (Grype):** JSON, SARIF, CycloneDX, table.
- **Agent wrapping:** Nice "SBOM-first" pipeline — generate SBOM once with Syft, reuse across Grype (vulns) and other consumers. Container-centric.

### Dependabot / Renovate (remediation, not detection)
- **Role:** Automated dependency-update **PR bots**, not scanners you parse. They *fix* what SCA finds.
- **Dependabot:** GitHub-native; `.github/dependabot.yml`; 30+ ecosystems (npm, pip, Maven, Gradle, Bundler, Cargo, Composer, NuGet, Go, Docker, Terraform, GitHub Actions, pnpm, Bun, Helm, Swift, uv…); free, minimal setup; grouping requires manual config.
- **Renovate:** 90+ managers, multi-platform (GitHub/GitLab/Bitbucket/Azure/Gitea), regex managers, merge-confidence scoring, out-of-the-box grouping. More powerful, more config.
- **Agent wrapping:** The agent can *generate/tune* a `dependabot.yml` or `renovate.json`, or open its own remediation PRs mirroring their behavior. Treat as the "fix" arm complementing OSV/Trivy's "find" arm.

---

## 3. Secrets detection

### Gitleaks
- **Checks:** Hardcoded secrets — API keys, tokens, passwords — in git history, working dir, or stdin. Regex + entropy rules, fully customizable.
- **Scope:** Language-agnostic (scans text). Modes: `git` (history), `dir` (files), `stdin`.
- **License:** Open source (MIT), ~26k★.
- **CLI / headless:** Yes. `gitleaks detect --report-format sarif --report-path out.sarif`.
- **Output:** JSON, CSV, JUnit, **SARIF**.
- **Agent wrapping:** Default secrets pass. Run over full history for audits, or diff-only in pre-commit mode. Trivy also does secrets if you want fewer tools; Gitleaks is the specialist with better history scanning and rule control.

---

## 4. IaC / misconfiguration (bonus class)

- **Checkov (Prisma/Bridgecrew):** 1,000+ policies for Terraform, CloudFormation, K8s, Dockerfile, Helm, ARM. Open source (Apache 2.0). CLI, JSON/SARIF output. Strong policy depth.
- **tfsec:** Terraform-focused misconfig scanner (now converging into Trivy). Open source.
- **Trivy `config`:** covers much of the same ground in the all-in-one binary.
- **Agent wrapping:** For repos with IaC, add Checkov or Trivy-config; parse SARIF alongside code findings.

---

## 5. Why SARIF matters for an agent

- **SARIF = Static Analysis Results Interchange Format**, an OASIS standard, JSON-based (current: v2.1.0). Designed so results from *different* tools are "universally understood" by IDEs / CI / dashboards.
- For Better-call-behdad this means **one ingestion path**: normalize every tool to SARIF `runs[].results[]` with `ruleId`, `level`, `message`, `locations[].physicalLocation` (file + region), and (for CodeQL) `codeFlows` (source→sink steps). Then the LLM reasons over a uniform structure regardless of which engine produced it.
- **Caveats:** SARIF can be lossy vs. a tool's native JSON (e.g. severity nuance, confidence, autofix). Strategy: prefer SARIF for cross-tool correlation, but keep the native JSON around when a field you need isn't in SARIF (Bandit confidence, Semgrep autofix, Snyk reachability).
- SARIF also has an **extension mechanism** (`properties` bags) tools use for custom data — the agent should read those, not just the core schema.

---

## 6. Patterns for combining deterministic tools + LLM reasoning

The consistent finding across 2025–2026 research and practice: **tools provide recall + ground truth; the LLM provides precision + explanation.** Neither alone is enough — SAST has high false-positive rates and no contextual understanding; LLMs hallucinate and are inconsistent. Combine them.

### Pattern A — Tool-as-ground-truth, LLM-as-triager (core loop)
1. Run deterministic tools (Semgrep/CodeQL/Bandit/ESLint/Trivy/Gitleaks…) → normalized SARIF findings with exact locations, rule IDs, CWEs.
2. For each finding, hand the LLM the *finding + surrounding code + dataflow path* and ask: **true positive or false positive? exploitable in this context? severity here?**
3. LLM outputs an adjudication + human-readable rationale, suppressing confirmed FPs.
- **Evidence:** *SAST-Genius* reduced false positives ~91% (225→20) vs. Semgrep alone. *ZeroFalse* treats analyzer output as a "structured contract" enriched with flow traces + CWE knowledge before LLM adjudication, cutting FPs while preserving coverage. *AdaTaint* cut triage time ~31% and raised analyst trust.

### Pattern B — LLM as cross-tool correlator / deduper
- The same real issue surfaces from Semgrep + CodeQL + Bandit under different rule IDs. The LLM clusters overlapping findings (same file/line/CWE), merges them into one ranked issue, and reconciles conflicting severities. Reduces noise the way no single tool can.

### Pattern C — LLM narration of dataflow
- CodeQL/Semgrep-Pro emit source→sink step paths. The LLM turns those machine steps into a plain-English "how the taint flows" explanation and a concrete fix + patch diff. High user value, low hallucination risk (grounded in tool-provided path).

### Pattern D — LLM as scope router / cost optimizer
- Run cheap/fast tools first (Ruff, ESLint, Gitleaks, OSV-Scanner) broadly; the LLM decides *where* to spend expensive passes (CodeQL DB build, Semgrep Pro interfile) — e.g., only on files/modules with initial hits or high churn.

### Pattern E — LLM as rule author
- Agent writes bespoke Semgrep YAML (or ESLint/CodeQL queries) for project-specific anti-patterns discovered during review, then re-runs deterministically so the *check itself* becomes reproducible ground truth rather than a one-off LLM opinion.

### Guardrails for the skill
- **Never let the LLM invent findings without a tool anchor** unless clearly labeled as "LLM-only heuristic (unverified)." Ground-truth findings and LLM speculation must be visually/structurally separated.
- **Keep the tool as arbiter of location/existence; keep the LLM as arbiter of relevance/severity/exploitability.**
- **Determinism where it counts:** re-runnable tool commands + pinned rulesets so an audit is reproducible; the LLM layer is the variable part.
- **Multi-agent fit:** natural split — one agent per signal class (SAST agent, SCA agent, secrets agent, IaC agent), each wrapping its tool(s) and emitting normalized SARIF, plus a triage/synthesis agent that runs Patterns A–D over the union.

---

## 7. Comparison table

| Tool | Class | Languages / scope | OSS vs commercial | Headless CLI | JSON | SARIF | Best agent role |
|---|---|---|---|---|---|---|---|
| **Semgrep CE** | SAST / patterns | 30+ langs, IaC, generic | OSS (Pro commercial) | Yes | Yes | Yes | Default broad SAST; custom rules |
| **CodeQL** | SAST / dataflow | C/C++, C#, Go, Java, Kotlin, Swift, Rust, JS/TS, Py, Ruby | Free (OSS-use; GHAS for closed-source) | Yes (DB build) | — | Yes | Deep pass; dataflow narration |
| **SonarQube (Community)** | Quality + security | 20+ (CE), 40+ (commercial) | OSS core; branch/PR commercial | Scanner posts to server | via API | limited | Read issues/quality-gate via API |
| **Bandit** | SAST (security) | Python | OSS | Yes | Yes | Yes | Fast Python security pass |
| **Ruff** | Lint / correctness | Python | OSS | Yes (very fast) | Yes | Yes | First fast broad gate; autofix |
| **ESLint** | Lint / correctness | JS/TS/JSX | OSS | Yes | Yes | Yes (formatter) | JS/TS correctness + security plugins |
| **OSV-Scanner** | SCA | 11+ langs, 19+ lockfiles, SBOM | OSS | Yes | Yes | Yes | Default free SCA |
| **Trivy** | SCA + IaC + secrets + container | very broad | OSS | Yes | Yes | Yes | All-in-one, uniform output |
| **Snyk** | SCA + SAST + IaC + container | broad (SCA); narrower SAST | Commercial (free tier) | Yes (auth) | Yes | Yes | When org already licensed |
| **OWASP Dependency-Check** | SCA | Java, .NET, npm, pip, Ruby, Go | OSS | Yes (NVD sync) | Yes | Yes | JVM/.NET shops |
| **Grype + Syft** | SBOM + SCA | OS + lang deps, images | OSS | Yes | Yes | Yes | SBOM-first container pipeline |
| **Gitleaks** | Secrets | language-agnostic + git history | OSS | Yes | Yes | Yes | Default secrets pass |
| **Checkov** | IaC misconfig | TF, CFN, K8s, Docker, Helm | OSS | Yes | Yes | Yes | IaC policy depth |
| **Dependabot** | Remediation (PRs) | 30+ ecosystems | Free (GitHub) | N/A (bot) | — | — | Generate/tune config; auto-fix arm |
| **Renovate** | Remediation (PRs) | 90+ managers, multi-SCM | OSS/SaaS | N/A (bot) | — | — | Advanced remediation config |

---

## 8. Recommended default stack for Better-call-behdad

A pragmatic, all-open-source, no-license-friction baseline the agent can invoke anywhere:

- **SAST:** Semgrep (broad) → CodeQL (deep, on hotspots) + Ruff/Bandit (Python) + ESLint (JS/TS).
- **SCA:** OSV-Scanner (primary) or Trivy `fs` (if you also want IaC/containers/secrets from one binary).
- **Secrets:** Gitleaks.
- **IaC/containers:** Trivy `config` and/or Checkov; Grype+Syft for images.
- **Remediation:** emit/tune `dependabot.yml` or open patch PRs.
- **Normalization:** everything → SARIF v2.1.0; retain native JSON for lossy fields.
- **LLM layer:** Patterns A (triage), B (dedup), C (narrate), D (route), E (author rules).

---

## Sources & links

**SAST / code patterns**
- Semgrep Community Edition — https://semgrep.dev/products/community-edition/
- Semgrep CLI reference — https://semgrep.dev/docs/cli-reference
- Semgrep repo — https://github.com/semgrep/semgrep
- CodeQL CLI overview — https://docs.github.com/en/code-security/codeql-cli/getting-started-with-the-codeql-cli/about-the-codeql-cli
- CodeQL SARIF output — https://docs.github.com/en/code-security/codeql-cli/using-the-advanced-functionality-of-the-codeql-cli/sarif-output
- CodeQL supported languages — https://codeql.github.com/docs/codeql-overview/supported-languages-and-frameworks/
- SonarScanner CLI / SonarQube — https://www.sonarsource.com/integrations/
- Bandit repo — https://github.com/PyCQA/bandit ; PyPI — https://pypi.org/project/bandit/
- Ruff repo — https://github.com/astral-sh/ruff ; docs — https://docs.astral.sh/ruff/
- ESLint formatters — https://eslint.org/docs/latest/use/formatters/ ; config — https://eslint.org/docs/latest/use/configure/configuration-files

**SCA / supply chain**
- OSV-Scanner repo — https://github.com/google/osv-scanner ; output docs — https://google.github.io/osv-scanner/output/ ; OSV.dev — https://osv.dev/
- Trivy repo — https://github.com/aquasecurity/trivy ; Aqua page — https://www.aquasec.com/products/trivy/
- Snyk CLI test — https://docs.snyk.io/developer-tools/snyk-cli/commands/test ; Snyk Code test — https://docs.snyk.io/developer-tools/snyk-cli/commands/code-test
- OWASP Dependency-Check — https://owasp.org/www-project-dependency-check/ ; CLI args — https://jeremylong.github.io/DependencyCheck/dependency-check-cli/arguments.html ; repo — https://github.com/dependency-check/DependencyCheck
- Grype — https://github.com/anchore/grype ; Syft — https://github.com/anchore/syft
- Dependabot vs Renovate — https://docs.renovatebot.com/bot-comparison/

**Secrets & IaC**
- Gitleaks repo — https://github.com/gitleaks/gitleaks
- Checkov (via comparison) — https://secure-pipelines.com/ci-cd-security/ci-cd-security-scanners-compared-trivy-grype-snyk-checkov/

**SARIF standard**
- SARIF v2.1.0 (OASIS) — https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
- Microsoft SARIF tutorials — https://github.com/microsoft/sarif-tutorials/blob/main/docs/1-Introduction.md
- Sonar SARIF guide — https://www.sonarsource.com/resources/library/sarif/

**LLM + SAST hybrid research**
- SAST-Genius (hybrid framework, ~91% FP reduction) — https://arxiv.org/abs/2509.15433
- ZeroFalse (LLM precision on static analysis) — https://arxiv.org/html/2510.02534
- AdaTaint (LLM-driven taint, ~31% faster triage) — https://dl.acm.org/doi/10.1145/3773365.3773410
- Sifting the Noise (LLM agents for FP filtering) — https://arxiv.org/html/2601.22952v1
- LLMs vs static code analysis benchmark — https://arxiv.org/pdf/2508.04448
