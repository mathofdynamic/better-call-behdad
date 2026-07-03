"""
score_run.py — score a Behdad run against a seeded repo's exhaustive ground truth.

Because tests/fixtures/seeded-repo/ground-truth.json lists EVERY real defect, any reported
finding that matches nothing in it is a false positive by construction — so precision and
recall come out of this script automatically, with no human triage sheet. (measure.py remains
the tool for real-world repos, where ground truth is unknown.)

  python scripts/score_run.py <report.json> --truth tests/fixtures/seeded-repo/ground-truth.json
         [--out scores.json]

Input: a report from aggregate.py (or a bare findings list). Output: a scorecard with
  recall            — planted bugs detected / planted bugs
  judgment_recall   — same, over judgment_only bugs (the LLM layer's own number)
  precision         — matched findings / reported findings
  trap_hits         — findings landing inside a noise trap (each one is a hard failure)
  critic_kill_rate  — rejected / all candidates, when the report carries an audit_trail
Exit code: 0 if recall == 1.0, precision == 1.0 and no trap hits; 1 otherwise. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _base(path: str) -> str:
    return (path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()


def matches(finding: dict, gt: dict) -> bool:
    if _base(finding.get("file", "")) != _base(gt["file"]):
        return False
    line = finding.get("line") or 0
    if gt.get("line") and abs(line - gt["line"]) > gt.get("line_tolerance", 3):
        return False
    accepted_cwes = gt.get("cwe") or []
    if accepted_cwes:
        return bool(set(accepted_cwes) & set(finding.get("canonical_ids") or []))
    # Judgment-only bugs carry no CWE: aspect + location is their identity. `aspect` may be a
    # list — a planted logic bug legitimately reported as e.g. security still counts as found.
    aspects = gt["aspect"] if isinstance(gt["aspect"], list) else [gt["aspect"]]
    return finding.get("aspect") in aspects


def in_trap(finding: dict, traps: list[dict]) -> dict | None:
    line = finding.get("line") or 0
    for t in traps:
        lo, hi = t["lines"]
        if _base(finding.get("file", "")) == _base(t["file"]) and lo <= line <= hi:
            return t
    return None


def score(report: dict | list, truth: dict) -> dict:
    findings = report["findings"] if isinstance(report, dict) else report
    planted = truth["planted"]
    traps = truth.get("noise_traps", [])

    detected: set[str] = set()
    trap_hits: list[dict] = []
    false_positives: list[dict] = []
    for f in findings:
        gt = next((g for g in planted if g["id"] not in detected and matches(f, g)), None)
        if gt:
            detected.add(gt["id"])
            continue
        t = in_trap(f, traps)
        brief = {"title": f.get("title", ""), "file": f.get("file", ""), "line": f.get("line")}
        if t:
            trap_hits.append({**brief, "trap": t["id"], "why_benign": t["why"]})
        else:
            false_positives.append(brief)

    judgment = [g for g in planted if g.get("judgment_only")]
    judgment_found = [g for g in judgment if g["id"] in detected]
    matched = len(detected)
    reported = len(findings)

    out = {
        "recall": round(len(detected) / len(planted), 3) if planted else None,
        "judgment_recall": round(len(judgment_found) / len(judgment), 3) if judgment else None,
        "precision": round(matched / reported, 3) if reported else None,
        "reported": reported,
        "planted": len(planted),
        "detected": sorted(detected),
        "missed": [{"id": g["id"], "title": g["title"]} for g in planted if g["id"] not in detected],
        "trap_hits": trap_hits,
        "false_positives": false_positives,
    }

    if isinstance(report, dict) and "audit_trail" in report:
        at = report["audit_trail"]
        rejected = at.get("rejected_count", 0)
        candidates = reported + rejected + at.get("abstained_count", 0) + at.get("suppressed_count", 0)
        out["critic_kill_rate"] = round(rejected / candidates, 3) if candidates else None
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Score a Behdad run against seeded ground truth")
    ap.add_argument("report", help="report JSON from aggregate.py (or a bare findings list)")
    ap.add_argument("--truth", required=True, help="ground-truth.json for the seeded repo")
    ap.add_argument("--out", help="also write the scorecard JSON here")
    args = ap.parse_args(argv)

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    truth = json.loads(Path(args.truth).read_text(encoding="utf-8"))
    card = score(report, truth)

    print("=== Behdad seeded-repo scorecard ===")
    for k in ("recall", "judgment_recall", "precision", "critic_kill_rate"):
        if k in card and card[k] is not None:
            print(f"  {k:18} {card[k]}")
    print(f"  {'reported':18} {card['reported']}  (planted: {card['planted']})")
    if card["missed"]:
        print("  MISSED:")
        for m in card["missed"]:
            print(f"    - {m['id']}: {m['title']}")
    if card["trap_hits"]:
        print("  NOISE-TRAP HITS (hard failures):")
        for t in card["trap_hits"]:
            print(f"    - {t['file']}:{t['line']} hit {t['trap']} ({t['why_benign']})")
    if card["false_positives"]:
        print("  FALSE POSITIVES:")
        for fp in card["false_positives"]:
            print(f"    - {fp['file']}:{fp['line']} {fp['title']}")

    if args.out:
        Path(args.out).write_text(json.dumps(card, indent=2), encoding="utf-8")
    perfect = card["recall"] == 1.0 and card["precision"] == 1.0 and not card["trap_hits"]
    return 0 if perfect else 1


if __name__ == "__main__":
    raise SystemExit(main())
