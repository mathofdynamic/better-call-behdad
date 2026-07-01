# 01 — Standards & Rubrics

Research brief for **Better-call-behdad**, a multi-agent code-audit skill. This document catalogs authoritative, checkable standards a code auditor should enforce. For each standard it flags what is **MACHINE-CHECKABLE** (deterministic tooling can verify it) vs. what needs **LLM JUDGMENT** (semantic/contextual reasoning). Primary sources are cited inline and collected at the end.

> **Legend**
> - 🤖 **MACHINE** — verifiable by a scanner/linter/CI tool with reproducible output (often SARIF).
> - 🧠 **JUDGMENT** — requires human/LLM reasoning about intent, design, or context; tools can hint but not decide.
> - Most real controls are **hybrid**: a tool flags candidates, an LLM adjudicates exploitability/relevance.

---

## 1. Security

### 1.1 OWASP Top 10 (2021)
The industry-standard awareness document for web-app risk. Ten categories ([owasp.org/Top10](https://owasp.org/Top10/2021/)):

| ID | Category |
|----|----------|
| A01:2021 | Broken Access Control |
| A02:2021 | Cryptographic Failures |
| A03:2021 | Injection (incl. XSS) |
| A04:2021 | Insecure Design |
| A05:2021 | Security Misconfiguration |
| A06:2021 | Vulnerable and Outdated Components |
| A07:2021 | Identification and Authentication Failures |
| A08:2021 | Software and Data Integrity Failures |
| A09:2021 | Security Logging and Monitoring Failures |
| A10:2021 | Server-Side Request Forgery (SSRF) |

- 🤖 **MACHINE:** Injection sinks (A03), known-vulnerable dependencies (A06, via SCA/CVE feeds), some misconfigurations (A05: debug flags, default creds, missing security headers), hard-coded secrets (A02), missing SSRF allowlists (pattern-level). SAST tools (Semgrep, CodeQL, SonarQube) map rules to these categories.
- 🧠 **JUDGMENT:** A01 Broken Access Control and A04 Insecure Design are largely **non-machine-checkable** — they require understanding of intended authorization model and business logic. A09 (is logging *adequate and meaningful*?) also needs judgment. OWASP itself notes access control and design flaws resist automated detection.
- **Note:** The Top 10 is an *awareness* list, not a testing checklist — use ASVS for verifiable requirements.

### 1.2 OWASP ASVS (Application Security Verification Standard)
The verifiable, requirement-level companion to the Top 10 — a testable checklist ([project page](https://owasp.org/www-project-application-security-verification-standard/)).
- **4.0.3** organizes ~286 requirements into 14 chapters (V1–V14) with three assurance **Levels**: L1 (low, mostly black-box/automatable), L2 (standard — recommended for most apps, adds manual/design review), L3 (high assurance — sensitive/regulated apps). Full text: [ASVS 4.0.3 PDF](https://github.com/OWASP/ASVS/raw/v4.0.3/4.0/OWASP%20Application%20Security%20Verification%20Standard%204.0.3-en.pdf).
- **5.0** (released 30 May 2025) restructured to **17 chapters (~350 requirements)**, adding standalone chapters for Web Frontend Security (V3), Self-Contained Tokens (V9), OAuth/OIDC (V10), and WebRTC (V17); split V5 into Encoding/Sanitization + Validation/Business Logic. L3 grew from ~20 to ~90 extra requirements. ([What's new in 5.0](https://softwaremill.com/whats-new-in-asvs-5-0/); [OWASP/ASVS repo](https://github.com/OWASP/ASVS)).
- 🤖 **MACHINE:** Many L1 controls (TLS config, cookie flags, header presence, password-policy enforcement, output encoding presence). ASVS explicitly tags which items are "penetration-testable without source access."
- 🧠 **JUDGMENT:** L2/L3 items about business-logic limits, design decisions, cryptographic *appropriateness*, and access-control correctness. Good rubric backbone: an auditor can cite an ASVS requirement ID (e.g., `V2.1.1`) for each finding.

### 1.3 CWE Top 25 Most Dangerous Software Weaknesses (2024)
MITRE/CISA-maintained, data-driven ranking derived from 31,770 CVEs (Jun 2023–Jun 2024). **Danger Score = frequency × severity (avg CVSS)** ([MITRE Top 25](https://cwe.mitre.org/top25/archive/2024/2024_cwe_top25.html); [CISA alert](https://www.cisa.gov/news-events/alerts/2024/11/20/2024-cwe-top-25-most-dangerous-software-weaknesses)).

| # | CWE | Weakness |
|---|-----|----------|
| 1 | CWE-79 | Cross-site Scripting (XSS) |
| 2 | CWE-787 | Out-of-bounds Write |
| 3 | CWE-89 | SQL Injection |
| 4 | CWE-352 | Cross-Site Request Forgery (CSRF) |
| 5 | CWE-22 | Path Traversal |
| 6 | CWE-125 | Out-of-bounds Read |
| 7 | CWE-78 | OS Command Injection |
| 8 | CWE-416 | Use After Free |
| 9 | CWE-862 | Missing Authorization |
| 10 | CWE-434 | Unrestricted Upload of Dangerous File Type |
| 11 | CWE-94 | Code Injection |
| 12 | CWE-20 | Improper Input Validation |
| 13 | CWE-77 | Command Injection |
| 14 | CWE-287 | Improper Authentication |
| 15 | CWE-269 | Improper Privilege Management |
| 16 | CWE-502 | Deserialization of Untrusted Data |
| 17 | CWE-200 | Exposure of Sensitive Information (new to top ranks) |
| 18 | CWE-863 | Incorrect Authorization |
| 19 | CWE-918 | Server-Side Request Forgery (SSRF) |
| 20 | CWE-119 | Improper Restriction of Ops within Memory Buffer |
| 21 | CWE-476 | NULL Pointer Dereference |
| 22 | CWE-798 | Use of Hard-coded Credentials |
| 23 | CWE-190 | Integer Overflow or Wraparound |
| 24 | CWE-400 | Uncontrolled Resource Consumption (new) |
| 25 | CWE-306 | Missing Authentication for Critical Function |

- 🤖 **MACHINE:** Memory-safety (787, 125, 416, 476, 119), injection (79, 89, 78, 77, 94), hard-coded creds (798), unsafe deserialization (502), integer overflow (190) — all have mature SAST/linters. CWE IDs are the canonical taxonomy for tagging every finding.
- 🧠 **JUDGMENT:** Authorization/authn weaknesses (862, 863, 287, 306, 269) — tools detect *missing* checks poorly; correctness needs context. **Best practice: tag every security finding with a CWE ID** for traceability regardless of who found it.

### 1.4 SANS / CWE Top 25 relationship
The "SANS Top 25" is the same list — historically **CWE/SANS Top 25**, developed by MITRE with the SANS Institute; now published as the CWE Top 25 ([sans.org/top25-software-errors](https://www.sans.org/top25-software-errors)). Legacy "**Monster Mitigations**" ([mitre.org/top25/mitigations](https://cwe.mitre.org/top25/mitigations.html)) map cross-cutting defenses (input validation, least privilege, safe APIs) to multiple weaknesses — useful as remediation groupings. Broader scope than OWASP Top 10 (covers desktop, embedded, network, not just web).

### 1.5 NIST SSDF — SP 800-218 (Secure Software Development Framework v1.1)
Outcome-based secure-SDLC practices, driven by EO 14028; de-facto mandatory for US federal software suppliers ([NIST SP 800-218 final](https://csrc.nist.gov/pubs/sp/800/218/final); [PDF](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf)). Four practice groups:
- **PO — Prepare the Organization** (define security requirements, roles, toolchains).
- **PS — Protect the Software** (protect code integrity, provenance, releases).
- **PW — Produce Well-Secured Software** (secure design, threat modeling, code review, SAST/DAST, secure defaults).
- **RV — Respond to Vulnerabilities** (identify, remediate, root-cause, disclose).
- 🤖 **MACHINE:** Presence of SAST/DAST/SCA in pipeline (PW.7/PW.8), signed artifacts/provenance (PS), dependency scanning (RV.1), SBOM generation. These are *process* checks (does the repo/CI configure these?).
- 🧠 **JUDGMENT:** Threat modeling quality (PW.1), adequacy of security requirements (PO.1), whether design mitigates identified risks. SSDF is a *process/governance* framework — mostly org-maturity judgment, not per-line code checks.

### 1.6 Supply-chain security & SLSA v1.0
[SLSA (Supply-chain Levels for Software Artifacts) v1.0](https://slsa.dev/spec/v1.0/levels) — a Build track with levels L0–L3 focused on provenance integrity (uses [in-toto attestation](https://slsa.dev/spec/v1.0/whats-new) format):
- **L0** none; **L1** scripted/consistent build + (unsigned) provenance describing build; **L2** hosted build platform + **signed** provenance (authenticity); **L3** hardened, isolated build + **unforgeable** provenance (keys inaccessible to build steps).
- 🤖 **MACHINE:** Provenance presence/format, signature verification (cosign/sigstore), build-platform attestations, reproducibility. Highly automatable in CI.
- 🧠 **JUDGMENT:** Whether the *threat model* justifies the target level; trust decisions about upstream sources.
- **Related:** SBOM standards — **SPDX** (ISO/IEC 5962:2021, license-focused) and **CycloneDX** (security/VEX-focused). 🤖 SBOM generation and policy checks (allowed/denied licenses, known CVEs) are fully automatable in CI. ([SBOM formats — Wiz](https://www.wiz.io/academy/application-security/standard-sbom-formats)).

### 1.7 Secrets management
[OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html); [OWASP DevSecOps Guideline](https://owasp.org/www-project-devsecops-guideline/latest/01a-Secrets-Management); [CI/CD Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html).
- Core rules: never hard-code secrets in code/CI config; centralize in a vault/secret manager; rotate machine credentials (NIST guidance: rotate user creds on suspected compromise, not on arbitrary schedule); least-privilege access; audit/log secret access.
- 🤖 **MACHINE:** Secret detection is one of the **most reliably automatable** checks. Layered approach: **Gitleaks** (150+ patterns, fast pre-commit hook), **TruffleHog** (800+ types across git/S3/Docker/etc., *verifies* if credential is live), plus platform push protection. Also entropy analysis and provider-specific regexes.
- 🧠 **JUDGMENT:** Distinguishing real secrets from test fixtures/placeholders (false-positive triage); whether rotation/vault architecture is adequate.

---

## 2. Code Quality & Maintainability

### 2.1 ISO/IEC 25010 — Product Quality Model
The global reference model ([iso.org/standard/78176](https://www.iso.org/standard/78176.html) for the **2023** revision; [ISO 25000 portal](https://iso25000.com/index.php/en/iso-25000-standards/iso-25010)). **Eight characteristics** (2023 revision; each with sub-characteristics):
1. **Functional Suitability** (completeness, correctness, appropriateness)
2. **Performance Efficiency** (time behavior, resource use, capacity)
3. **Compatibility** (co-existence, interoperability)
4. **Interaction Capability / Usability** (learnability, accessibility, UI aesthetics)
5. **Reliability** (maturity, availability, fault tolerance, recoverability)
6. **Security** (confidentiality, integrity, non-repudiation, accountability, authenticity)
7. **Maintainability** (modularity, reusability, analyzability, modifiability, testability)
8. **Portability** (adaptability, installability, replaceability)
   *(2023 revision also adds/renames **Safety** as a characteristic.)*
- 🤖 **MACHINE:** Maintainability sub-characteristics proxy well to metrics (modularity → coupling/cohesion; analyzability → complexity/size; testability → coverage). Performance/reliability partially measurable via benchmarks.
- 🧠 **JUDGMENT:** Functional suitability (does it meet requirements?), appropriateness, and overall trade-offs. 25010 is a *vocabulary/framework* for organizing an audit rubric — not directly measurable itself; it defines *what* to measure, not thresholds. ([arc42 quality model](https://quality.arc42.org/standards/iso-25010)).

### 2.2 SOLID principles (Robert C. Martin)
Five OO design principles ([Clean Coders ep. 8](https://cleancoders.com/episode/clean-code-episode-8); [DigitalOcean overview](https://www.digitalocean.com/community/conceptual-articles/s-o-l-i-d-the-first-five-principles-of-object-oriented-design)):
- **S**ingle Responsibility — a class has one reason to change.
- **O**pen/Closed — open for extension, closed for modification.
- **L**iskov Substitution — subtypes substitutable for base types.
- **I**nterface Segregation — no forced dependency on unused interfaces.
- **D**ependency Inversion — depend on abstractions, not concretions.
- 🤖 **MACHINE:** Weak proxies only — e.g., large class / god-object detection (SRP hint via LCOM cohesion metric, method/field counts), fan-in/fan-out (DIP hints), interface size (ISP hints). Architecture-fitness tools (ArchUnit, dependency-cruiser, NDepend) can enforce layering rules that *encode* DIP.
- 🧠 **JUDGMENT:** SOLID compliance is **primarily judgment** — "one reason to change" and "correct abstraction" require semantic understanding. This is a prime LLM-reviewer area.

### 2.3 Clean Code & code smells
Robert C. Martin, *Clean Code* ([ACM entry](https://dl.acm.org/doi/10.5555/1388398)); classic smell catalog (also Fowler). Smells: duplicated code, long functions/methods, long parameter lists, large classes, feature envy, inappropriate intimacy, primitive obsession, dead code, magic numbers, comments-as-deodorant. Design smells (Martin): **Rigidity, Fragility, Immobility, Viscosity, Needless Complexity, Needless Repetition, Opacity**.
- 🤖 **MACHINE:** Duplicated code (copy-paste detectors: PMD CPD, SonarQube), long method/large class (line/statement thresholds), long parameter lists, dead code, magic numbers, high nesting — all standard linter rules.
- 🧠 **JUDGMENT:** Feature envy, inappropriate intimacy, wrong abstraction, misleading names, "needless complexity" — need semantic reasoning about intent.

### 2.4 Cyclomatic complexity (McCabe)
Counts independent paths through code ([Microsoft Learn: cyclomatic complexity](https://learn.microsoft.com/en-us/visualstudio/code-quality/code-metrics-cyclomatic-complexity)). Thresholds:
- **McCabe's original recommendation: split modules exceeding CC 10.** Some teams tolerate up to 15.
- Microsoft's **CA1502** analyzer flags CC **> 25** by default (more permissive).
- NDepend: CC 15 = hard to maintain; CC > 30 = extremely complex, should be split. ([NDepend](https://blog.ndepend.com/understanding-cyclomatic-complexity/)).
- 🤖 **MACHINE:** Fully automatable — every major linter/metric tool computes it (radon for Python, ESLint complexity rule, SonarQube, lizard, gocyclo). **Recommended default gate: warn > 10, fail > 15–20 (configurable).** Also cognitive complexity (SonarQube's more human-oriented variant).
- 🧠 **JUDGMENT:** Whether a high-CC function is *justified* (e.g., a parser/state machine) vs. genuinely needs refactoring.

### 2.5 Maintainability Index (MI)
Composite metric (Oman & Hagemeister, 1992) combining **Halstead Volume + Cyclomatic Complexity + Lines of Code** ([Microsoft Learn: MI range](https://learn.microsoft.com/en-us/visualstudio/code-quality/code-metrics-maintainability-index-range-and-meaning)):
- Microsoft rebases to 0–100: **0–9 red (low)**, **10–19 yellow (moderate)**, **20–100 green (good)**.
- NDepend variant: >50 OK, >80 great. ([NDepend MI](https://blog.ndepend.com/maintainability-index/)).
- 🤖 **MACHINE:** Fully automatable (Visual Studio, radon, `mi` tools). Useful as a trend/regression gate.
- 🧠 **JUDGMENT:** MI is a coarse heuristic — low absolute value doesn't always mean bad code; use as a signal, not a verdict.

### 2.6 Google Engineering Practices (industry engineering-practice guide)
Google's public [eng-practices](https://google.github.io/eng-practices/) — the [Code Review Developer Guide](https://google.github.io/eng-practices/review/) is a strong rubric. Reviewers examine: **design, functionality, complexity, tests, naming, comments, style, documentation** ([What to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html)). Guiding standard ([The Standard of Code Review](https://google.github.io/eng-practices/review/reviewer/standard.html)): *approve once the change definitely improves overall code health, even if imperfect.* Warns against **over-engineering** (solve today's problem, not speculative futures); style guide is authoritative for required items. Also *Software Engineering at Google* book, [Ch.9 Code Review](https://abseil.io/resources/swe-book/html/ch09.html).
- 🤖 **MACHINE:** Style conformance (formatters/linters: gofmt, prettier, clang-format, black), presence of tests, doc updates when public API changes.
- 🧠 **JUDGMENT:** Design appropriateness, "could this be simpler?", naming quality, comment usefulness, over-engineering — the core of what an LLM reviewer contributes. This guide is an excellent template for structuring an LLM audit agent's dimensions.

---

## 3. Testing

### 3.1 Test pyramid
Fowler's [Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html): many fast **unit** tests (base), fewer **integration/service** tests (middle), few slow **E2E/UI** tests (top). Common heuristic ~**70/20/10**. Gov reference: [UK Home Office Test Pyramid standard](https://engineering.homeoffice.gov.uk/standards/test-pyramid/).
- 🤖 **MACHINE:** Test counts by type/directory, execution time distribution, ratio computation — measurable if tests are categorized. CI can enforce ratios.
- 🧠 **JUDGMENT:** Whether tests are *meaningful* (not just asserting mocks), test-boundary correctness, whether the pyramid shape fits the system (microservices may need more contract tests).

### 3.2 Coverage types
Metrics: **line/statement, branch/decision, function, condition, path, MC/DC** (aviation DO-178C). Coverage tools (JaCoCo, coverage.py, Istanbul/nyc, gcov) emit these.
- 🤖 **MACHINE:** Coverage % computation and thresholds are fully automatable and CI-gateable (e.g., fail if < 80% line / < 70% branch). Diff/patch coverage (Codecov) gates new code.
- 🧠 **JUDGMENT:** **High coverage ≠ good tests** — coverage says lines *ran*, not that behavior was *asserted*. Judging assertion quality and edge-case coverage needs reasoning. Avoid treating a single coverage number as sufficient.

### 3.3 Mutation testing
Injects small faults ("mutants"); a good suite should "kill" them (fail). **Mutation score = killed/total** — measures test *effectiveness*, addressing coverage's blind spot. Tools: **PIT/Pitest** (Java), **Stryker** (JS/TS/C#/Scala), **mutmut**/**cosmic-ray** (Python), **mutation-testing** in general.
- 🤖 **MACHINE:** Mutation score is computable and gateable, though expensive (slow). A strong quantitative signal of test quality.
- 🧠 **JUDGMENT:** Interpreting surviving mutants (equivalent mutants are false positives) and prioritizing which to address.

---

## 4. Accessibility, Licensing/Compliance, Documentation

### 4.1 Accessibility — WCAG 2.2
W3C standard ([WCAG 2.2 spec](https://www.w3.org/TR/WCAG22/)). Organized under **POUR**: **P**erceivable, **O**perable, **U**nderstandable, **R**obust. Three conformance levels — **A** (baseline), **AA** (legal target for Section 508, EN 301 549, ADA — 56 criteria cumulative), **AAA** (highest). Levels are cumulative (AA includes A).
- 🤖 **MACHINE:** ~30–40% of criteria are auto-testable: missing `alt` text, form-label association, color-contrast ratios, ARIA validity, heading order, `lang` attribute, keyboard focusability. Tools: **axe-core**, **Lighthouse**, **Pa11y**, **WAVE** (emit structured/SARIF-like results).
- 🧠 **JUDGMENT:** Majority need manual/LLM review: is alt text *meaningful*, is focus order *logical*, are error messages *understandable*, is content operable by screen reader in practice. Automated tools catch a minority of real WCAG failures.

### 4.2 Licensing / Compliance
- **SPDX** ([ISO/IEC 5962:2021](https://spdx.dev/)) — standardized license identifiers (`SPDX-License-Identifier: MIT`) and SBOM format; **CycloneDX** — security-oriented SBOM. ([SBOM formats — Wiz](https://www.wiz.io/academy/application-security/standard-sbom-formats)).
- License classes: **permissive** (MIT, Apache-2.0, BSD), **weak copyleft** (LGPL, MPL — linking OK), **strong copyleft** (GPL, AGPL — viral). Typical policy: allow permissive, conditionally allow weak copyleft, forbid strong copyleft/unknown in proprietary code.
- 🤖 **MACHINE:** License detection and policy enforcement are **highly automatable**: **ScanCode Toolkit**, **FOSSology**, **FOSSA**, **Snyk**, GitLab license scanning, `licensee`. CI can fail builds on disallowed/unknown licenses and generate SBOMs per PR. Also: presence of a LICENSE file, SPDX headers, copyright notices.
- 🧠 **JUDGMENT:** License *compatibility* analysis (does combining these licenses create a conflict?), attribution completeness, and whether usage triggers copyleft obligations — legal-flavored reasoning.

### 4.3 Documentation completeness
No single ISO standard, but consensus checklists exist ([README best practices](https://www.welcometothejungle.com/en/articles/btc-readme-documentation-best-practices); [API doc quality checklist — I'd Rather Be Writing](https://idratherbewriting.com/learnapidoc/docapis_quality_checklist.html)).
- **README essentials:** project purpose/overview, install/setup, usage/quickstart, configuration, contributing guide, license, contact/support. **API docs:** reference (all endpoints/params/responses/errors), auth methods, runnable examples, changelog, OpenAPI/Swagger spec. Parameter docs: description, type, min/max, sample, required/optional.
- 🤖 **MACHINE:** Presence checks — LICENSE, README with required headings, CONTRIBUTING, CHANGELOG, OpenAPI spec validity; docstring/public-API coverage (interrogate for Python, JSDoc coverage, doc-coverage linters); broken-link checkers; spec-vs-implementation drift.
- 🧠 **JUDGMENT:** Is documentation *accurate, clear, and complete* for the audience? The strongest completeness test ("can a new dev implement using only the docs?") is inherently a reasoning task.

---

## 5. Machine-checkable vs. LLM-judgment — summary matrix

| Area | Mostly 🤖 MACHINE | Mostly 🧠 JUDGMENT |
|------|------------------|---------------------|
| Security | Injection sinks, known-CVE deps (SCA), secrets (Gitleaks/TruffleHog), memory-safety, missing headers/TLS, SBOM/provenance | Broken access control, insecure design, authz correctness, logging *adequacy*, threat-model quality |
| Code quality | Cyclomatic/cognitive complexity, MI, duplication, dead code, long method/class, style/format | SOLID adherence, naming, right abstraction, over-engineering, clean-code smells (feature envy) |
| Testing | Coverage %, mutation score, test-type ratios, execution time | Test meaningfulness, assertion quality, edge-case adequacy, pyramid fit |
| Accessibility | alt/labels/contrast/ARIA/heading order (axe, Lighthouse) | Meaningful alt text, logical focus order, understandable errors |
| Licensing | License detection, policy gates, SBOM gen, LICENSE/header presence | License compatibility/legal analysis, attribution completeness |
| Documentation | Presence of files/sections, docstring coverage, OpenAPI validity, dead links | Accuracy, clarity, "can a newcomer build from this?" |

**Design takeaways for Better-call-behdad:**
1. **Tag every finding** with a canonical ID (CWE-###, OWASP A##/ASVS V#.#.#, WCAG SC #.#.#) for traceability and dedup across agents.
2. **Two-phase pattern:** run deterministic tools first (SARIF-normalized output from Semgrep/CodeQL/SonarQube, Gitleaks, coverage tools, axe, ScanCode), then have LLM agents adjudicate exploitability, false positives, and the judgment-heavy dimensions tools can't touch.
3. **Ground rubric dimensions in ISO/IEC 25010** characteristics; use **Google eng-practices** as the code-review dimension template; use **ASVS** as the security requirement checklist.
4. Prefer **primary/official sources** (OWASP, MITRE/CISA, NIST, W3C, ISO, SLSA, Google) over blog thresholds; where thresholds vary (e.g., complexity), make them **configurable with cited defaults**.

---

## Sources & Links

**Security**
- OWASP Top 10:2021 — https://owasp.org/Top10/2021/
- OWASP ASVS project — https://owasp.org/www-project-application-security-verification-standard/ ; 4.0.3 PDF — https://github.com/OWASP/ASVS/raw/v4.0.3/4.0/OWASP%20Application%20Security%20Verification%20Standard%204.0.3-en.pdf ; repo — https://github.com/OWASP/ASVS ; ASVS 5.0 changes — https://softwaremill.com/whats-new-in-asvs-5-0/
- CWE Top 25 (2024) — https://cwe.mitre.org/top25/archive/2024/2024_cwe_top25.html ; CISA alert — https://www.cisa.gov/news-events/alerts/2024/11/20/2024-cwe-top-25-most-dangerous-software-weaknesses ; ranked list — https://www.helpnetsecurity.com/2024/11/21/cwe-top-25-most-dangerous-software-weaknesses/
- SANS Top 25 — https://www.sans.org/top25-software-errors ; CWE/SANS Monster Mitigations — https://cwe.mitre.org/top25/mitigations.html
- NIST SSDF SP 800-218 — https://csrc.nist.gov/pubs/sp/800/218/final ; PDF — https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf
- SLSA v1.0 levels — https://slsa.dev/spec/v1.0/levels ; what's new — https://slsa.dev/spec/v1.0/whats-new
- OWASP Secrets Management Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html ; DevSecOps Guideline — https://owasp.org/www-project-devsecops-guideline/latest/01a-Secrets-Management ; CI/CD Security Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html
- SBOM formats (SPDX/CycloneDX) — https://www.wiz.io/academy/application-security/standard-sbom-formats

**Code Quality & Maintainability**
- ISO/IEC 25010:2023 — https://www.iso.org/standard/78176.html ; portal — https://iso25000.com/index.php/en/iso-25000-standards/iso-25010 ; arc42 — https://quality.arc42.org/standards/iso-25010
- SOLID (Clean Coders) — https://cleancoders.com/episode/clean-code-episode-8 ; overview — https://www.digitalocean.com/community/conceptual-articles/s-o-l-i-d-the-first-five-principles-of-object-oriented-design
- Clean Code (ACM) — https://dl.acm.org/doi/10.5555/1388398
- Cyclomatic complexity (MS Learn) — https://learn.microsoft.com/en-us/visualstudio/code-quality/code-metrics-cyclomatic-complexity ; NDepend — https://blog.ndepend.com/understanding-cyclomatic-complexity/
- Maintainability Index (MS Learn) — https://learn.microsoft.com/en-us/visualstudio/code-quality/code-metrics-maintainability-index-range-and-meaning ; NDepend — https://blog.ndepend.com/maintainability-index/
- Google eng-practices — https://google.github.io/eng-practices/ ; Code Review standard — https://google.github.io/eng-practices/review/reviewer/standard.html ; What to look for — https://google.github.io/eng-practices/review/reviewer/looking-for.html ; SWE at Google Ch.9 — https://abseil.io/resources/swe-book/html/ch09.html

**Testing**
- Practical Test Pyramid (Fowler) — https://martinfowler.com/articles/practical-test-pyramid.html ; UK Home Office standard — https://engineering.homeoffice.gov.uk/standards/test-pyramid/

**Accessibility / Licensing / Documentation**
- WCAG 2.2 — https://www.w3.org/TR/WCAG22/
- SPDX — https://spdx.dev/ ; SBOM/license standards — https://www.wiz.io/academy/application-security/standard-sbom-formats
- README best practices — https://www.welcometothejungle.com/en/articles/btc-readme-documentation-best-practices ; API doc quality checklist — https://idratherbewriting.com/learnapidoc/docapis_quality_checklist.html
- Static analysis tool comparison (Semgrep/SonarQube/CodeQL, SARIF) — https://rafter.so/blog/static-code-analysis-tools-comparison
