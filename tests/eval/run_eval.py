"""
run_eval.py — Behdad's evaluation harness + KPI gate.

Exercises the DETERMINISTIC layers (the parts we can test headlessly) and prints a scorecard:
  1. Normalizer unit checks  — canned tool outputs -> correct Behdad findings (no tools needed).
  2. Aggregate KPI checks     — dedup / ranking / gating on synthetic findings.
  3. Seeded-repo E2E scan     — run installed scanners on the seeded repo; assert planted issues
                                are found and noise-traps are NOT (skips gracefully if no scanners).
  4. Config-sync check        — config/severity.yaml numbers match aggregate.py constants.

The LLM orchestration (inspectors/critic/manager) is validated separately in a live agent session;
this harness locks down the deterministic scaffolding those agents stand on.

Exit code 0 = all gates pass; 1 = a gate failed. Stdlib only.
Run:  python tests/eval/run_eval.py
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

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))


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
        check("E2E scan (needs bandit)", True, "SKIPPED — bandit not installed; degraded gracefully")
        return
    env = run_scanners.scan(seeded, depth="quick", timeout=120, allow_code_execution=False)
    findings = env["findings"]
    cwes = {c for f in findings for c in f.get("canonical_ids", [])}
    files_lines = {(Path(f["file"]).name, f["line"]) for f in findings}

    check("E2E: SQL injection (CWE-89) found", "CWE-89" in cwes, sorted(cwes))
    check("E2E: command injection / dangerous call (CWE-78) found", "CWE-78" in cwes)
    check("E2E: weak crypto (CWE-327) found", "CWE-327" in cwes)
    check("E2E: hardcoded secret found (CWE-259/798)", bool({"CWE-259", "CWE-798"} & cwes))

    # Noise-traps: the benign helpers must NOT be flagged. They live near the end of app.py.
    # Assert no finding lands on the safe_total/format_name bodies (lines >= 38).
    trap_hits = [fl for fl in files_lines if fl[0] == "app.py" and fl[1] >= 38]
    check("E2E: noise-traps (safe_total/format_name) NOT flagged", not trap_hits, str(trap_hits))

    # KPI proxy on a known repo: bandit is high-recall/low-precision, so raw findings are many;
    # this harness asserts the *planted* issues are all captured (recall on the seeded set = 100%).
    check("E2E: honest missing-tools reporting", isinstance(env["tools_missing"], list))


# --- 4. Config-sync check -----------------------------------------------------------------

def test_config_sync() -> None:
    sev = (ROOT / "config" / "severity.yaml").read_text(encoding="utf-8")
    ok = (
        "critical: 1.00" in sev
        and f"min_to_report: {aggregate.MIN_TO_REPORT}" in sev
        and f"default_when_unknown: {aggregate.EPSS_DEFAULT}" in sev
    )
    check("config: severity.yaml numbers match aggregate.py constants", ok,
          "update aggregate.py constants if you edited severity.yaml")


def main() -> int:
    for t in (test_normalizer, test_aggregate, test_seeded_repo, test_config_sync):
        try:
            t()
        except Exception as exc:  # a crashing test is a failure, not a harness abort
            check(t.__name__, False, f"raised {type(exc).__name__}: {exc}")

    print("\n=== Behdad evaluation scorecard ===")
    width = max(len(n) for _, n, _ in results)
    for status, name, detail in results:
        mark = "OK" if status == PASS else "XX"
        print(f"  [{mark}] {name.ljust(width)}  {('-- ' + str(detail)) if detail else ''}")
    failed = [r for r in results if r[0] == FAIL]
    total = len(results)
    print(f"\n{total - len(failed)}/{total} checks passed.")
    if failed:
        print("FAILURES:", ", ".join(n for _, n, _ in failed))
        return 1
    print("All deterministic gates green.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
