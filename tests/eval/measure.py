"""
measure.py — before/after measurement harness for a real Behdad run.

Turns "did it do well?" into numbers. Three subcommands:

  snapshot   Capture a project's objective state (raw scanner findings + test result + git commit).
             Run it BEFORE Behdad and AFTER remediation to get the two ends of the comparison.

  compare    Diff two snapshots → findings resolved / still-present / newly-introduced, test-status
             change, and the noise-reduction ratio if a Behdad report is supplied. This is the
             objective "before/after" scorecard.

  triage     From Behdad's report.json, emit a human triage sheet (mark each finding TP/FP/unsure)
             plus a JSON skeleton. Fill in the verdicts, then:

  score      Read the filled triage JSON → precision, signal ratio, false-positive count, all
             checked against the KPI targets.

Stdlib only. Reuses run_scanners for the raw scan.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import run_scanners  # noqa: E402

# KPI targets (from the plan / research baselines).
KPI = {"signal_ratio_min": 0.50, "max_false_positives": 5, "human_agreement_min": 0.85}


def _git_commit(target: Path) -> str:
    try:
        p = subprocess.run(["git", "-C", str(target), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=15)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def _run_tests(target: Path, cmd: str | None) -> dict:
    if not cmd:
        return {"ran": False, "passed": None, "cmd": None}
    try:
        p = subprocess.run(cmd, cwd=str(target), shell=True, capture_output=True,
                           text=True, timeout=900)
        return {"ran": True, "passed": p.returncode == 0, "cmd": cmd, "rc": p.returncode,
                "tail": (p.stdout + p.stderr)[-500:].strip()}
    except subprocess.TimeoutExpired:
        return {"ran": True, "passed": False, "cmd": cmd, "rc": -1, "tail": "timeout"}


def _finding_key(f: dict) -> str:
    # Identity that survives line shifts after fixes: file basename + rule + first CWE.
    fname = Path(f.get("file", "")).name
    cwe = (f.get("canonical_ids") or [""])[0]
    return f"{fname}|{f.get('rule_id','')}|{cwe}"


def snapshot(target: Path, label: str, tests: str | None, depth: str) -> dict:
    env = run_scanners.scan(target, depth=depth, timeout=180, allow_code_execution=False)
    findings = env["findings"]
    by_sev = Counter(f.get("severity", "info") for f in findings)
    by_tool = Counter(f.get("source", "?") for f in findings)
    return {
        "label": label,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "target": str(target),
        "git_commit": _git_commit(target),
        "raw_finding_count": len(findings),
        "by_severity": dict(by_sev),
        "by_tool": dict(by_tool),
        "tools_used": env["tools_used"],
        "tools_missing": [m["id"] for m in env["tools_missing"]],
        "finding_keys": sorted(_finding_key(f) for f in findings),
        "tests": _run_tests(target, tests),
    }


def compare(before: dict, after: dict, report: dict | None) -> dict:
    b, a = Counter(before["finding_keys"]), Counter(after["finding_keys"])
    resolved = list((b - a).elements())      # in before, gone after
    introduced = list((a - b).elements())    # new in after
    persistent = list((b & a).elements())

    out = {
        "raw_findings_before": before["raw_finding_count"],
        "raw_findings_after": after["raw_finding_count"],
        "resolved": len(resolved),
        "introduced": len(introduced),
        "persistent": len(persistent),
        "resolved_examples": resolved[:10],
        "introduced_examples": introduced[:10],  # NEW findings = a fix may have caused a regression
        "severity_before": before["by_severity"],
        "severity_after": after["by_severity"],
        "tests_before": before["tests"],
        "tests_after": after["tests"],
    }
    # Test regression flag: was passing, now failing.
    tb, ta = before["tests"], after["tests"]
    if tb.get("passed") and ta.get("passed") is False:
        out["test_regression"] = True
    # Axis ① noise reduction, if a Behdad report is supplied.
    if report is not None:
        reported = len(report.get("findings", []))
        raw = before["raw_finding_count"]
        out["noise_reduction"] = {
            "raw_scanner_findings": raw,
            "behdad_reported_findings": reported,
            "filtered_out": raw - reported,
            "reduction_pct": round(100 * (raw - reported) / raw, 1) if raw else 0.0,
            "note": "How much of the raw scanner noise Behdad's precision layer removed.",
        }
    return out


def triage(report: dict) -> tuple[str, dict]:
    findings = report.get("findings", [])
    lines = ["# Behdad triage sheet",
             "> Mark each finding: TP (real), FP (false positive), or ? (unsure).",
             "> Then run: python tests/eval/measure.py score triage.json", ""]
    skeleton = {"verdicts": []}
    for i, f in enumerate(findings, 1):
        fid = f.get("id", f"f{i}")
        loc = f"{Path(f.get('file','')).name}:{f.get('line',0)}"
        lines.append(f"{i:>2}. [ TP / FP / ? ]  ({f.get('severity','?')}) {loc}  "
                     f"{(f.get('title') or f.get('evidence',''))[:70]}")
        skeleton["verdicts"].append({"id": fid, "loc": loc,
                                     "severity": f.get("severity"), "verdict": "?"})
    lines.append("")
    lines.append(f"Total reported: {len(findings)}")
    return "\n".join(lines), skeleton


def score(triage_marked: dict) -> dict:
    v = triage_marked.get("verdicts", [])
    tp = sum(1 for x in v if str(x.get("verdict", "")).upper() == "TP")
    fp = sum(1 for x in v if str(x.get("verdict", "")).upper() == "FP")
    unsure = sum(1 for x in v if x.get("verdict") not in ("TP", "FP", "tp", "fp"))
    judged = tp + fp
    precision = round(tp / judged, 3) if judged else 0.0
    signal_ratio = round(tp / len(v), 3) if v else 0.0
    return {
        "total_reported": len(v),
        "true_positives": tp,
        "false_positives": fp,
        "unsure": unsure,
        "precision": precision,               # TP / (TP+FP)
        "signal_ratio": signal_ratio,         # TP / total reported
        "kpi": {
            "signal_ratio": f"{signal_ratio} (target >= {KPI['signal_ratio_min']}) "
                            f"{'PASS' if signal_ratio >= KPI['signal_ratio_min'] else 'MISS'}",
            "false_positives": f"{fp} (target <= {KPI['max_false_positives']}) "
                               f"{'PASS' if fp <= KPI['max_false_positives'] else 'MISS'}",
        },
    }


def _load(p: str) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Behdad before/after measurement harness")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("snapshot")
    ps.add_argument("target")
    ps.add_argument("--label", default="before")
    ps.add_argument("--tests", default=None, help="Test command, e.g. 'pytest -q'")
    ps.add_argument("--depth", default="quick")
    ps.add_argument("--out", required=True)

    pc = sub.add_parser("compare")
    pc.add_argument("before"); pc.add_argument("after")
    pc.add_argument("--report", default=None, help="Behdad report.json for noise-reduction metric")
    pc.add_argument("--out", default=None)

    pt = sub.add_parser("triage")
    pt.add_argument("report"); pt.add_argument("--sheet", required=True)
    pt.add_argument("--json", required=True)

    psc = sub.add_parser("score")
    psc.add_argument("triage_json")

    args = ap.parse_args(argv)

    if args.cmd == "snapshot":
        snap = snapshot(Path(args.target).resolve(), args.label, args.tests, args.depth)
        Path(args.out).write_text(json.dumps(snap, indent=2), encoding="utf-8")
        print(f"[{snap['label']}] {snap['raw_finding_count']} raw findings "
              f"{snap['by_severity']} | tools={snap['tools_used']} | "
              f"tests={'pass' if snap['tests'].get('passed') else snap['tests'].get('passed')}")
    elif args.cmd == "compare":
        out = compare(_load(args.before), _load(args.after),
                      _load(args.report) if args.report else None)
        text = json.dumps(out, indent=2)
        (Path(args.out).write_text(text, encoding="utf-8") if args.out else None)
        print(text)
    elif args.cmd == "triage":
        sheet, skeleton = triage(_load(args.report))
        Path(args.sheet).write_text(sheet, encoding="utf-8")
        Path(args.json).write_text(json.dumps(skeleton, indent=2), encoding="utf-8")
        print(f"wrote triage sheet -> {args.sheet} and skeleton -> {args.json}")
    elif args.cmd == "score":
        print(json.dumps(score(_load(args.triage_json)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
