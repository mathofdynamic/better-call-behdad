"""
aggregate.py — Behdad's deterministic consolidation engine.

The manager could eyeball dedup/ranking, but math is exactly what an LLM should NOT do by hand.
This module takes the findings emitted by inspectors + the critic and deterministically:
  1. drops non-reportable findings (rejected / abstain / suppressed / below confidence gate),
  2. dedups by (canonical_ids, file, line), merging sources and computing an agreement ratio,
  3. computes a blended risk_score (severity x EPSS-ish x reachability x aspect-scale),
  4. ranks, and
  5. emits a report skeleton conforming to schemas/report.schema.json.

The numeric constants MIRROR config/severity.yaml (kept here so the engine is stdlib-only and
needs no YAML parser). If you change severity.yaml, update SEVERITY below to match. A sync test
lives in tests/eval/. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# --- constants mirrored from config/severity.yaml -----------------------------------------

SEVERITY_WEIGHT = {"critical": 1.00, "high": 0.75, "medium": 0.50, "low": 0.25, "info": 0.05}

EPSS_DEFAULT = 0.30
EPSS_CATEGORY_PRIORS = {
    "CWE-89": 0.70, "CWE-79": 0.60, "CWE-78": 0.70, "CWE-22": 0.55,
    "CWE-502": 0.65, "CWE-798": 0.60, "CWE-306": 0.55,
}

ENVIRONMENTAL = {
    "reachable_from_entrypoint": 1.00,
    "reachable_internal_only": 0.60,
    "reachability_unknown": 0.50,
    "unreachable_dead_code": 0.10,
}

NON_SECURITY_SCALE = {
    "security": 1.00, "logic": 0.90, "supply-chain": 0.90,
    "quality": 0.55, "testing": 0.55, "performance": 0.60, "accessibility": 0.50,
}

MIN_TO_REPORT = 0.55
GROUND_TRUTH_BYPASS = True
ABSTAIN_SHOWN = False

SEC_ASPECTS = {"security", "supply-chain"}


# --- helpers ------------------------------------------------------------------------------

def _epss_factor(aspect: str, canonical_ids: list[str]) -> float:
    """Approximate exploit-likelihood factor. Security/supply-chain use CWE priors; others n/a."""
    if aspect not in SEC_ASPECTS:
        return 1.0
    best = EPSS_DEFAULT
    for cid in canonical_ids or []:
        if cid in EPSS_CATEGORY_PRIORS:
            best = max(best, EPSS_CATEGORY_PRIORS[cid])
    return best


def _environmental_factor(finding: dict) -> float:
    v = finding.get("verification") or {}
    reachable = v.get("reachable", None)
    if reachable is True:
        return ENVIRONMENTAL["reachable_from_entrypoint"]
    if reachable is False:
        return ENVIRONMENTAL["unreachable_dead_code"]
    return ENVIRONMENTAL["reachability_unknown"]


def risk_score(finding: dict) -> float:
    aspect = finding.get("aspect", "quality")
    base = SEVERITY_WEIGHT.get(finding.get("severity", "medium"), 0.50)
    epss = _epss_factor(aspect, finding.get("canonical_ids") or [])
    env = _environmental_factor(finding)
    scale = NON_SECURITY_SCALE.get(aspect, 0.55)
    return round(base * epss * env * scale, 4)


def _dedup_key(f: dict) -> tuple:
    cids = tuple(sorted(f.get("canonical_ids") or []))
    return (f.get("aspect"), cids, f.get("file", ""), f.get("line", 0))


def _reportable(f: dict) -> bool:
    status = f.get("status", "candidate")
    if status in ("rejected", "suppressed"):
        return False
    if status == "abstain" and not ABSTAIN_SHOWN:
        return False
    conf = float(f.get("confidence", 0) or 0)
    if conf < MIN_TO_REPORT:
        if not (GROUND_TRUTH_BYPASS and f.get("ground_truth")):
            return False
    return True


def _merge(group: list[dict]) -> dict:
    """Merge duplicate findings: union sources, keep strongest, compute agreement."""
    # Prefer the finding with the most evidence / highest confidence as the base.
    base = max(group, key=lambda g: (len(g.get("evidence", "")), float(g.get("confidence", 0) or 0)))
    base = dict(base)
    sources: list[str] = []
    for g in group:
        for s in g.get("detected_by", []) or []:
            if s not in sources:
                sources.append(s)
    base["detected_by"] = sources
    base["confidence"] = max(float(g.get("confidence", 0) or 0) for g in group)
    # Agreement: 2+ independent sources => full consensus; 1 source => 0.5.
    distinct = len(sources)
    base["agreement"] = round(min(1.0, distinct / 2.0), 3) if distinct else 0.0
    base["risk_score"] = risk_score(base)
    return base


def aggregate(findings: list[dict]) -> dict:
    reportable = [f for f in findings if _reportable(f)]
    rejected = sum(1 for f in findings if f.get("status") == "rejected")
    abstained = sum(1 for f in findings if f.get("status") == "abstain")
    suppressed = sum(1 for f in findings if f.get("status") == "suppressed")

    # Dedup.
    groups: dict[tuple, list[dict]] = {}
    for f in reportable:
        groups.setdefault(_dedup_key(f), []).append(f)
    merged = [_merge(g) for g in groups.values()]

    # Rank: risk desc, then agreement*confidence desc.
    merged.sort(
        key=lambda f: (f["risk_score"], f.get("agreement", 0) * float(f.get("confidence", 0) or 0)),
        reverse=True,
    )

    # Summary counts.
    by_sev: dict[str, int] = {}
    by_aspect: dict[str, int] = {}
    for f in merged:
        by_sev[f.get("severity", "info")] = by_sev.get(f.get("severity", "info"), 0) + 1
        by_aspect[f.get("aspect", "?")] = by_aspect.get(f.get("aspect", "?"), 0) + 1
    overall_conf = round(sum(float(f.get("confidence", 0) or 0) for f in merged) / len(merged), 3) if merged else 0.0

    # Action plan skeleton (ordered by rank).
    action_plan = []
    for i, f in enumerate(merged, start=1):
        action_plan.append({
            "order": i,
            "finding_id": f.get("id", ""),
            "action": (f.get("explanation_for_humans") or f.get("title") or "Review and fix.")[:300],
            "risk": f"{f.get('severity','?')} / risk={f['risk_score']}",
            "auto_fixable": bool(f.get("proposed_fix")),
            "effort": "small",
        })

    return {
        "schema_version": "1.0",
        "summary": {
            "headline": _headline(by_sev, len(merged)),
            "counts_by_severity": by_sev,
            "counts_by_aspect": by_aspect,
            "overall_confidence": overall_conf,
        },
        "findings": merged,
        "action_plan": action_plan,
        "audit_trail": {
            "rejected_count": rejected,
            "abstained_count": abstained,
            "suppressed_count": suppressed,
        },
    }


def _headline(by_sev: dict, total: int) -> str:
    if total == 0:
        return "No verified issues surfaced. The audited scope looks healthy (see coverage caveats)."
    crit = by_sev.get("critical", 0)
    high = by_sev.get("high", 0)
    lead = "Critical issues need attention before shipping." if crit else (
        "High-severity issues found." if high else "Some issues found; none critical.")
    return f"{lead} {total} verified finding(s): " + ", ".join(f"{n} {s}" for s, n in by_sev.items()) + "."


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Behdad deterministic aggregation engine")
    ap.add_argument("findings", help="JSON file: a flat list of findings (post-critic)")
    ap.add_argument("--out", help="Write report JSON here (default: stdout)")
    ap.add_argument("--target", default="", help="Target repo path (for report.target)")
    ap.add_argument("--depth", default="quick")
    ap.add_argument("--raw-count", type=int, default=None,
                    help="Raw scanner finding count (from scan.json) — enables the auto noise-reduction metric")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    # Accept either a bare list or a scan envelope with a "findings" key.
    findings = data["findings"] if isinstance(data, dict) else data
    report = aggregate(findings)
    report["target"] = {"path": args.target}
    report.setdefault("scope", {"languages": [], "aspects_run": [], "depth": args.depth})

    # Self-reported measurement: how much raw scanner noise the precision layer removed.
    # This makes "how did it do?" part of the skill's own output — no external tool needed.
    if args.raw_count is not None:
        reported = len(report["findings"])
        filtered = max(0, args.raw_count - reported)
        report["measurement"] = {
            "raw_scanner_findings": args.raw_count,
            "reported_findings": reported,
            "filtered_as_noise": filtered,
            "noise_reduction_pct": round(100 * filtered / args.raw_count, 1) if args.raw_count else 0.0,
            "rejected_by_critic": report["audit_trail"].get("rejected_count", 0),
            "abstained": report["audit_trail"].get("abstained_count", 0),
        }

    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        s = report["summary"]
        print(f"{report['audit_trail']} | reportable={len(report['findings'])} | {s['counts_by_severity']}")
        print(s["headline"])
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
