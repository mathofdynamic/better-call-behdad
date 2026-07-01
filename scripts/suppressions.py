"""
suppressions.py — Behdad's "learn from rejections" store.

When a user dismisses a finding (false positive, intended design, won't-fix), we persist a
fingerprint to <target>/.behdad/suppressions.json so the same finding is auto-suppressed on
future runs. This is how a team tunes out recurring noise without editing the skill — one of the
FP-reduction levers both research efforts highlighted.

Fingerprint = aspect + sorted canonical_ids + file (LINE IS EXCLUDED on purpose, so edits above
the finding don't resurrect it). A suppression with empty canonical_ids matches by aspect+file+title.
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _store_path(target: Path) -> Path:
    return target / ".behdad" / "suppressions.json"


def load(target: Path) -> list[dict]:
    p = _store_path(target)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("suppressions", []) if isinstance(data, dict) else data
    except Exception:
        return []


def fingerprint(finding: dict) -> dict:
    return {
        "aspect": finding.get("aspect", ""),
        "canonical_ids": sorted(finding.get("canonical_ids") or []),
        "file": (finding.get("file") or "").replace("\\", "/"),
        "title": finding.get("title", ""),
    }


def _matches(finding: dict, supp: dict) -> bool:
    fp = fingerprint(finding)
    if fp["aspect"] != supp.get("aspect"):
        return False
    if fp["file"] != (supp.get("file") or "").replace("\\", "/"):
        return False
    s_ids = sorted(supp.get("canonical_ids") or [])
    if s_ids:  # match by canonical IDs when present (line-independent)
        return fp["canonical_ids"] == s_ids
    # else fall back to title match
    return fp["title"] == supp.get("title", "")


def is_suppressed(finding: dict, suppressions: list[dict]) -> bool:
    return any(_matches(finding, s) for s in suppressions)


def apply(findings: list[dict], target: Path) -> list[dict]:
    """Mark matching findings as status=suppressed (aggregate.py then drops them)."""
    supps = load(target)
    if not supps:
        return findings
    for f in findings:
        if is_suppressed(f, supps):
            f["status"] = "suppressed"
    return findings


def add(target: Path, finding: dict, reason: str = "") -> None:
    p = _store_path(target)
    p.parent.mkdir(exist_ok=True)
    supps = load(target)
    entry = fingerprint(finding)
    entry["reason"] = reason
    # Avoid exact duplicates.
    if not any(_matches(finding, s) for s in supps):
        supps.append(entry)
    p.write_text(json.dumps({"version": "1.0", "suppressions": supps}, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Behdad suppression store")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("add", help="Add a suppression from a finding JSON")
    pa.add_argument("--target", required=True)
    pa.add_argument("--finding", required=True, help="Path to a JSON file with the finding")
    pa.add_argument("--reason", default="")

    pl = sub.add_parser("list", help="List current suppressions")
    pl.add_argument("--target", required=True)

    pf = sub.add_parser("apply", help="Mark suppressed findings in a findings JSON list")
    pf.add_argument("--target", required=True)
    pf.add_argument("--findings", required=True)
    pf.add_argument("--out", required=True)

    args = ap.parse_args(argv)
    target = Path(args.target).resolve()

    if args.cmd == "add":
        finding = json.loads(Path(args.finding).read_text(encoding="utf-8"))
        add(target, finding, args.reason)
        print(f"suppression added for {fingerprint(finding)}")
    elif args.cmd == "list":
        print(json.dumps(load(target), indent=2))
    elif args.cmd == "apply":
        findings = json.loads(Path(args.findings).read_text(encoding="utf-8"))
        out = apply(findings, target)
        Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"marked {sum(1 for f in out if f.get('status')=='suppressed')} suppressed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
