"""
validate.py — lightweight runtime validation of findings and reports at the pipeline seams.

The JSON Schemas in schemas/ are the contracts, but nothing used to enforce them at runtime, so
a drifting inspector (wrong enum, missing field, string line number) silently corrupted the
report. This module checks the fields that matter for aggregation/scoring — not full JSON-Schema
(that would need a dependency) — and returns per-item reasons instead of crashing, so the
aggregator can drop-and-count invalid findings honestly.

  python scripts/validate.py <findings-or-report.json>   # CLI: prints problems, exit 1 if any

Stdlib only. Keep the enums in sync with schemas/finding.schema.json (the eval asserts this).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ASPECTS = {"security", "quality", "logic", "performance", "testing", "supply-chain",
           "accessibility"}
SEVERITIES = {"critical", "high", "medium", "low", "info"}
STATUSES = {"candidate", "verified", "rejected", "abstain", "suppressed"}

REQUIRED = ("id", "aspect", "title", "severity", "confidence", "file", "evidence", "status")


def finding_problems(f: dict) -> list[str]:
    """Return a list of contract violations for one finding (empty = valid)."""
    if not isinstance(f, dict):
        return ["finding is not an object"]
    probs: list[str] = []
    for key in REQUIRED:
        if key not in f or f[key] in (None, ""):
            probs.append(f"missing required field '{key}'")
    if f.get("aspect") not in ASPECTS:
        probs.append(f"aspect '{f.get('aspect')}' not in {sorted(ASPECTS)}")
    if f.get("severity") not in SEVERITIES:
        probs.append(f"severity '{f.get('severity')}' not in {sorted(SEVERITIES)}")
    if f.get("status") not in STATUSES:
        probs.append(f"status '{f.get('status')}' not in {sorted(STATUSES)}")
    conf = f.get("confidence")
    if not isinstance(conf, (int, float)) or not (0 <= float(conf) <= 1):
        probs.append(f"confidence '{conf}' is not a number in [0,1]")
    line = f.get("line")
    if line is not None and (not isinstance(line, int) or line < 0):
        probs.append(f"line '{line}' is not a non-negative integer")
    cids = f.get("canonical_ids")
    if cids is not None and (not isinstance(cids, list)
                             or any(not isinstance(c, str) for c in cids)):
        probs.append("canonical_ids is not a list of strings")
    return probs


def split_valid(findings: list) -> tuple[list[dict], list[dict]]:
    """Partition findings into (valid, invalid); each invalid entry carries its reasons."""
    valid: list[dict] = []
    invalid: list[dict] = []
    for i, f in enumerate(findings):
        probs = finding_problems(f)
        if probs:
            invalid.append({"index": i, "id": (f.get("id") if isinstance(f, dict) else None),
                            "problems": probs})
        else:
            valid.append(f)
    return valid, invalid


def report_problems(report: dict) -> list[str]:
    """Contract check for an aggregate.py report envelope."""
    probs: list[str] = []
    for key in ("schema_version", "summary", "findings", "action_plan", "audit_trail"):
        if key not in report:
            probs.append(f"missing report field '{key}'")
    if not isinstance(report.get("findings", []), list):
        probs.append("report.findings is not a list")
    return probs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate Behdad findings/report JSON")
    ap.add_argument("path", help="a findings list, scan envelope, or report JSON")
    args = ap.parse_args(argv)
    data = json.loads(Path(args.path).read_text(encoding="utf-8"))

    if isinstance(data, dict) and "audit_trail" in data:  # a report
        probs = report_problems(data)
        findings = data.get("findings", [])
    elif isinstance(data, dict):  # a scan envelope (or unknown dict)
        probs = [] if "findings" in data else ["no 'findings' key in JSON object"]
        findings = data.get("findings", [])
    else:
        probs = []
        findings = data if isinstance(data, list) else []

    _, invalid = split_valid(findings)
    for p in probs:
        print(f"REPORT: {p}")
    for inv in invalid:
        print(f"FINDING[{inv['index']}] ({inv['id']}): " + "; ".join(inv["problems"]))
    total = len(probs) + len(invalid)
    print(f"{total} problem(s) in {args.path}" if total else f"OK: {args.path} is valid")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
