"""
run_eval.py — Behdad's evaluation harness + KPI gate.

Exercises the DETERMINISTIC layers (the parts we can test headlessly) and prints a scorecard:
  1. Normalizer unit checks  — canned tool outputs -> correct Behdad findings (no tools needed).
  2. Aggregate KPI checks     — dedup / ranking / gating on synthetic findings.
  3. Seeded-repo E2E scan     — run installed scanners on the seeded repo; assert planted issues
                                are found and noise-traps are NOT (skips gracefully if no scanners).
  4. Config-sync check        — config/severity.yaml numbers match aggregate.py constants.
  5. Fix-gate decision table  — the PreToolUse gate blocks every known bypass class and
                                allows the legitimate audit workflow (tests/eval/test_gate.py).

The LLM orchestration (inspectors/critic/manager) is validated separately in a live agent session;
this harness locks down the deterministic scaffolding those agents stand on.

Exit code 0 = all gates pass; 1 = a gate failed. Checks that need a scanner that is not
installed are reported as explicit [--] SKIP lines (never silently passed); use --strict or
BEHDAD_EVAL_STRICT=1 to turn skips into failures (recommended for CI). Stdlib only.
Run:  python tests/eval/run_eval.py [--strict]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

# Convenience: on Windows, pip-installed scanners often land in a Scripts dir not on PATH.
_extra = Path.home() / "AppData" / "Roaming" / "Python" / f"Python{sys.version_info.major}{sys.version_info.minor}" / "Scripts"
if _extra.exists():
    os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + str(_extra)

import aggregate  # noqa: E402
import sarif_normalize as norm  # noqa: E402
import run_scanners  # noqa: E402
import tool_registry as reg  # noqa: E402

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))


def skip(name: str, why: str) -> None:
    results.append((SKIP, name, why))


# --- 1. Normalizer unit checks ------------------------------------------------------------

def test_normalizer() -> None:
    bandit = {"results": [{
        "test_id": "B608", "issue_severity": "MEDIUM", "issue_confidence": "MEDIUM",
        "issue_cwe": {"id": 89}, "filename": "app.py", "line_number": 18,
        "issue_text": "Possible SQL injection",
    }]}
    b = norm.from_bandit(bandit)
    check("bandit: CWE-89 parsed from issue_cwe.id",
          b and b[0]["canonical_ids"] == ["CWE-89"] and b[0]["severity"] == "medium",
          str(b[0]["canonical_ids"]) if b else "no output")

    gitleaks = [{"Description": "AWS key", "RuleID": "aws-access-token", "File": "app.py", "StartLine": 5}]
    g = norm.from_gitleaks(gitleaks)
    check("gitleaks: secret -> CWE-798 high",
          g and g[0]["canonical_ids"] == ["CWE-798"] and g[0]["severity"] == "high")

    osv = {"results": [{"source": {"path": "requirements.txt"}, "packages": [{
        "package": {"name": "requests", "version": "2.19.0"},
        "vulnerabilities": [{"id": "GHSA-xxxx", "summary": "SSRF in requests",
                             "severity": [{"score": "HIGH"}], "aliases": ["CVE-2018-18074"]}],
    }]}]}
    o = norm.from_osv(osv)
    check("osv: vuln -> high, carries CVE in message",
          o and o[0]["severity"] == "high" and "CVE-2018-18074" in o[0]["message"])

    sarif = {"runs": [{"tool": {"driver": {"rules": [
        {"id": "sqli", "properties": {"security-severity": "9.1", "tags": ["CWE-89"]}}]}},
        "results": [{"ruleId": "sqli", "message": {"text": "SQL injection"},
                     "locations": [{"physicalLocation": {
                         "artifactLocation": {"uri": "app.py"}, "region": {"startLine": 18}}}]}]}]}
    s = norm.from_sarif(sarif, "semgrep")
    check("sarif: security-severity 9.1 -> critical, CWE from tags",
          s and s[0]["severity"] == "critical" and "CWE-89" in s[0]["canonical_ids"] and s[0]["line"] == 18)

    ruff = [{"code": "S101", "filename": "app.py", "location": {"row": 11}, "message": "assert used"}]
    r = norm.from_ruff(ruff)
    check("ruff: security rule S* bumped to medium", r and r[0]["severity"] == "medium")

    gosec = {"Issues": [{"severity": "HIGH", "cwe": {"id": "78"}, "rule_id": "G204",
                         "details": "Subprocess launched with variable", "file": "main.go",
                         "line": "42-43"}]}
    gs = norm.from_gosec(gosec)
    check("gosec: issue -> CWE-78 high at first line of range",
          gs and gs[0]["canonical_ids"] == ["CWE-78"] and gs[0]["severity"] == "high"
          and gs[0]["line"] == 42, str(gs)[:100])


# --- 2. Aggregate KPI checks --------------------------------------------------------------

def test_aggregate() -> None:
    findings = [
        {"id": "a", "aspect": "security", "title": "SQLi", "canonical_ids": ["CWE-89"],
         "severity": "high", "confidence": 0.95, "file": "app.py", "line": 18, "evidence": "x",
         "detected_by": ["bandit"], "status": "verified", "ground_truth": True,
         "verification": {"reachable": True}},
        {"id": "a2", "aspect": "security", "title": "SQLi dup", "canonical_ids": ["CWE-89"],
         "severity": "high", "confidence": 0.9, "file": "app.py", "line": 18, "evidence": "y",
         "detected_by": ["semgrep"], "status": "verified", "ground_truth": True,
         "verification": {"reachable": True}},
        {"id": "b", "aspect": "quality", "title": "nit", "severity": "low", "confidence": 0.4,
         "file": "app.py", "line": 2, "evidence": "z", "detected_by": ["q"],
         "status": "candidate", "ground_truth": False},  # below gate, non-ground-truth -> dropped
        {"id": "c", "aspect": "logic", "title": "maybe", "severity": "medium", "confidence": 0.3,
         "file": "app.py", "line": 9, "evidence": "?", "detected_by": ["l"],
         "status": "abstain", "ground_truth": False},  # abstain -> dropped
    ]
    rep = aggregate.aggregate(findings)
    ids_89 = [f for f in rep["findings"] if "CWE-89" in f.get("canonical_ids", [])]
    check("aggregate: duplicate SQLi merged to one", len(ids_89) == 1)
    check("aggregate: merged agreement == 1.0 (2 sources)", ids_89 and ids_89[0]["agreement"] == 1.0)
    check("aggregate: low-conf non-ground-truth dropped", all(f["id"] != "b" for f in rep["findings"]))
    check("aggregate: abstain dropped + counted",
          all(f["id"] != "c" for f in rep["findings"]) and rep["audit_trail"]["abstained_count"] == 1)
    # KPI proxy: with clean synthetic input, reportable set is exactly the real issues (no noise).
    check("KPI: reportable count == real issues (1)", len(rep["findings"]) == 1,
          f"got {len(rep['findings'])}")
    # Ranking sanity: reachable high-EPSS SQLi has a positive risk score.
    check("aggregate: risk_score computed", ids_89 and ids_89[0]["risk_score"] > 0)


# --- 3. Seeded-repo E2E scan --------------------------------------------------------------

def test_seeded_repo() -> None:
    seeded = ROOT / "tests" / "fixtures" / "seeded-repo"
    installed = {t.id for t in reg.available_tools()}
    if "bandit" not in installed:
        skip("E2E scan (needs bandit)", "bandit not installed — install it or run with --strict in CI")
        return
    # Scan a STAGED copy (like /behdad eval): outside the skill's own git repo — semgrep's
    # default ignore list skips tests/** paths, which would silently blank this whole fixture.
    import tempfile

    import stage_eval
    staged = Path(tempfile.mkdtemp(prefix="behdad_eval_")) / "seeded"
    stage_eval.stage(seeded, staged)
    env = run_scanners.scan(staged, depth="quick", timeout=300, allow_code_execution=False)
    findings = env["findings"]
    cwes = {c for f in findings for c in f.get("canonical_ids", [])}
    files_lines = {(Path(f["file"]).name, f["line"]) for f in findings}

    check("E2E: SQL injection (CWE-89) found", "CWE-89" in cwes, sorted(cwes))
    check("E2E: command injection / dangerous call (CWE-78) found", "CWE-78" in cwes)
    check("E2E: weak crypto (CWE-327) found", "CWE-327" in cwes)
    check("E2E: hardcoded secret found (CWE-259/798)", bool({"CWE-259", "CWE-798"} & cwes))
    # bandit tags eval() (B307) as CWE-78, semgrep as CWE-95 — assert by location + family.
    eval_hits = [f for f in findings if Path(f["file"]).name == "app.py"
                 and abs((f.get("line") or 0) - 34) <= 1
                 and {"CWE-95", "CWE-78"} & set(f.get("canonical_ids") or [])]
    check("E2E: eval on user input found at app.py:34 (CWE-95/78)", bool(eval_hits))

    # Noise-traps: the benign helpers must NOT be flagged. They live near the end of app.py.
    # Assert no finding lands on the safe_total/format_name bodies (lines >= 38).
    trap_hits = [fl for fl in files_lines if fl[0] == "app.py" and fl[1] >= 38]
    check("E2E: noise-traps (safe_total/format_name) NOT flagged", not trap_hits, str(trap_hits))

    # billing.py holds JUDGMENT-ONLY logic bugs: if any scanner flags it, they are not
    # judgment-only and the LLM-layer eval (ground-truth.json) is mislabeled.
    billing_hits = [fl for fl in files_lines if fl[0] == "billing.py"]
    check("E2E: billing.py logic bugs invisible to scanners (judgment-only)",
          not billing_hits, str(billing_hits))

    # Multi-language routing: the planted JS eval() must be caught (semgrep, zero-config)…
    if "semgrep" in {t for t in env["tools_used"]}:
        js = [f for f in findings if Path(f["file"]).name == "app.js"]
        check("E2E: JS eval (CWE-95) found in static/app.js",
              any(abs((f.get("line") or 0) - 13) <= 2
                  and "CWE-95" in (f.get("canonical_ids") or []) for f in js),
              str([(f.get('line'), f.get('canonical_ids')) for f in js]))
        # …the textContent noise-trap must NOT be flagged, and the innerHTML XSS must NOT be
        # scanner-detected (it is planted as judgment-only for the LLM eval).
        check("E2E: JS textContent trap not flagged (lines 16-19)",
              not any(16 <= (f.get("line") or 0) <= 19 for f in js))
        check("E2E: JS innerHTML XSS stays judgment-only (no scanner CWE-79)",
              not any("CWE-79" in (f.get("canonical_ids") or []) for f in js))
    else:
        skip("E2E JS checks (needs semgrep)", "semgrep not installed")

    # KPI proxy on a known repo: bandit is high-recall/low-precision, so raw findings are many;
    # this harness asserts the *planted* issues are all captured (recall on the seeded set = 100%).
    check("E2E: honest missing-tools reporting", isinstance(env["tools_missing"], list))


# --- 4. Fix-gate decision table -------------------------------------------------------------

def test_gate() -> None:
    sys.path.insert(0, str(ROOT / "tests" / "eval"))
    import test_gate as tg
    for ok, name, detail in tg.run_cases() + tg.run_subprocess_smoke():
        check(name, ok, detail)


# --- 5. Scorer determinism (the LLM-layer eval's measuring stick) ---------------------------

def test_scorer() -> None:
    import json

    import score_run

    truth = json.loads((ROOT / "tests" / "fixtures" / "seeded-repo" / "ground-truth.json")
                       .read_text(encoding="utf-8"))

    def f(file, line, cwes=None, aspect="security", title="x"):
        return {"file": file, "line": line, "canonical_ids": cwes or [], "aspect": aspect,
                "title": title, "severity": "high"}

    # A perfect run: one finding per planted bug, nothing else.
    perfect = [
        f("app.py", 12, ["CWE-798"]), f("app.py", 18, ["CWE-89"]), f("app.py", 24, ["CWE-78"]),
        f("app.py", 29, ["CWE-327"]), f("app.py", 34, ["CWE-95"]),
        f("static/app.js", 13, ["CWE-95"]), f("static/app.js", 8, ["CWE-79"]),
        f("billing.py", 26, aspect="logic"), f("billing.py", 35, aspect="logic"),
        f("billing.py", 45, aspect="logic"),
    ]
    n_planted = len(truth["planted"])
    card = score_run.score(perfect, truth)
    check("scorer: perfect run -> recall 1.0", card["recall"] == 1.0, str(card["recall"]))
    check("scorer: perfect run -> judgment_recall 1.0", card["judgment_recall"] == 1.0)
    check("scorer: perfect run -> precision 1.0, no traps",
          card["precision"] == 1.0 and not card["trap_hits"])

    # A flawed run: one planted bug missed, one FP, one noise-trap hit, a line-tolerance match.
    flawed = perfect[:-1] + [                       # gt-103 missed
        f("app.py", 99, title="invented issue"),    # FP (matches nothing)
        f("billing.py", 53, aspect="logic"),        # lands in nt-003 (half-open-range trap)
    ]
    flawed[1] = f("app.py", 20, ["CWE-89"])          # 2 lines off gt-002 -> still matches (tol 3)
    card = score_run.score(flawed, truth)
    check(f"scorer: flawed run -> recall {n_planted - 1}/{n_planted}",
          card["recall"] == round((n_planted - 1) / n_planted, 3), str(card["recall"]))
    check("scorer: flawed run -> 1 FP + 1 trap hit",
          len(card["false_positives"]) == 1 and len(card["trap_hits"]) == 1,
          f"fp={len(card['false_positives'])} traps={len(card['trap_hits'])}")
    check("scorer: line tolerance matches near hit", "gt-002" in card["detected"])
    check("scorer: missed list names gt-103",
          [m["id"] for m in card["missed"]] == ["gt-103"], str(card["missed"]))

    # critic_kill_rate comes from the report's audit trail.
    rep = {"findings": perfect, "audit_trail": {"rejected_count": 2, "abstained_count": 0,
                                                 "suppressed_count": 0}}
    card = score_run.score(rep, truth)
    expected_kill = round(2 / (len(perfect) + 2), 3)
    check("scorer: critic_kill_rate = rejected/candidates",
          card["critic_kill_rate"] == expected_kill, str(card.get("critic_kill_rate")))


# --- 6. Config-sync check -----------------------------------------------------------------

def test_config_sync() -> None:
    # aggregate.py now PARSES severity.yaml at runtime; assert the parser read real values
    # (not the hardcoded fallbacks) by checking a few knowns from the file.
    check("config: severity.yaml parsed at runtime",
          aggregate.SEVERITY_WEIGHT.get("critical") == 1.0
          and aggregate.MIN_TO_REPORT == 0.55
          and aggregate.EPSS_CATEGORY_PRIORS.get("CWE-89") == 0.70
          and aggregate.ENVIRONMENTAL.get("unreachable_dead_code") == 0.10,
          f"weights={aggregate.SEVERITY_WEIGHT}")
    # Regression guard: edit-detection — a value changed in the file must flow through.
    parsed = aggregate._load_flat_yaml(ROOT / "config" / "severity.yaml")
    check("config: flat-YAML reader handles nesting",
          parsed["epss"]["category_priors"]["CWE-78"] == 0.70
          and parsed["confidence_gate"]["ground_truth_bypass"] is True)


# --- 7. Precision-engine checks (proximity dedup, validation seam, complexity) --------------

def test_precision_engine() -> None:
    def f(id_, line, aspect="security", cids=None, conf=0.9, **kw):
        base = {"id": id_, "aspect": aspect, "title": id_, "canonical_ids": cids or ["CWE-89"],
                "severity": "high", "confidence": conf, "file": "app.py", "line": line,
                "evidence": "e", "detected_by": [id_], "status": "verified",
                "ground_truth": True}
        base.update(kw)
        return base

    # Proximity dedup: scanner at line 18, LLM anchored 2 lines away -> ONE finding.
    rep = aggregate.aggregate([f("scanner", 18), f("llm", 20, ground_truth=False)])
    check("dedup: near-line duplicates merge (±3 window)", len(rep["findings"]) == 1,
          f"got {len(rep['findings'])}")
    # But distinct defects further apart stay separate.
    rep = aggregate.aggregate([f("a", 18), f("b", 30)])
    check("dedup: distant findings stay separate", len(rep["findings"]) == 2)

    # Validation seam: a malformed finding is dropped and counted, not crashed on.
    bad = {"id": "bad", "aspect": "nonsense", "severity": "høj", "confidence": "high"}
    rep = aggregate.aggregate([f("good", 18), bad])
    check("validate: malformed finding dropped + counted",
          len(rep["findings"]) == 1 and rep["audit_trail"]["invalid_count"] == 1,
          str(rep["audit_trail"].get("invalid", []))[:120])

    # Effort derivation: no patch -> medium; one-liner -> trivial.
    rep = aggregate.aggregate([f("nofix", 18), f("oneliner", 40, proposed_fix="x = 1")])
    efforts = {a["finding_id"]: a["effort"] for a in rep["action_plan"]}
    check("effort: derived from proposed fix (not hardcoded)",
          efforts.get("nofix") == "medium" and efforts.get("oneliner") == "trivial",
          str(efforts))

    # Complexity counter: a function with 12 branch points crosses the warn threshold.
    import ast
    src = "def f(x):\n" + "".join(f"    if x > {i}: x += 1\n" for i in range(12)) + "    return x\n"
    cc = run_scanners._cyclomatic(ast.parse(src).body[0])
    check("complexity: cyclomatic counter (12 ifs -> 13)", cc == 13, f"got {cc}")

    # mypy normalizer: text lines -> findings.
    m = norm.from_mypy_text('app.py:7: error: Unsupported operand types [operator]\n'
                            'app.py:7: note: context line\n')
    check("mypy: text output normalized (notes dropped)",
          len(m) == 1 and m[0]["line"] == 7 and m[0]["rule_id"] == "operator", str(m)[:100])


def main(argv: list[str] | None = None) -> int:
    strict = "--strict" in (argv or sys.argv[1:]) or os.environ.get("BEHDAD_EVAL_STRICT") == "1"
    for t in (test_normalizer, test_aggregate, test_seeded_repo, test_gate, test_scorer,
              test_config_sync, test_precision_engine):
        try:
            t()
        except Exception as exc:  # a crashing test is a failure, not a harness abort
            check(t.__name__, False, f"raised {type(exc).__name__}: {exc}")

    print("\n=== Behdad evaluation scorecard ===")
    width = max(len(n) for _, n, _ in results)
    for status, name, detail in results:
        mark = {PASS: "OK", FAIL: "XX", SKIP: "--"}[status]
        print(f"  [{mark}] {name.ljust(width)}  {('-- ' + str(detail)) if detail else ''}")
    failed = [r for r in results if r[0] == FAIL]
    skipped = [r for r in results if r[0] == SKIP]
    if skipped and strict:
        failed += skipped
    total = len(results)
    print(f"\n{total - len(failed) - (0 if strict else len(skipped))}/{total} checks passed"
          + (f", {len(skipped)} skipped ({'FAIL under --strict' if strict else 'install the missing tools for full coverage'})"
             if skipped else "") + ".")
    if failed:
        print("FAILURES:", ", ".join(n for _, n, _ in failed))
        return 1
    print("All deterministic gates green.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
