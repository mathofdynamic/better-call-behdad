"""
aggregate.py — Behdad's deterministic consolidation engine.

The manager could eyeball dedup/ranking, but math is exactly what an LLM should NOT do by hand.
This module takes the findings emitted by inspectors + the critic and deterministically:
  1. drops non-reportable findings (rejected / abstain / suppressed / below confidence gate),
  2. dedups by (canonical_ids, file, line), merging sources and computing an agreement ratio,
  3. computes a blended risk_score (severity x EPSS-ish x reachability x aspect-scale),
  4. ranks, and
  5. emits a report skeleton conforming to schemas/report.schema.json.

The numeric model comes from config/severity.yaml, parsed AT RUNTIME by the minimal flat-YAML
reader below (the file is plain `key: value` two levels deep — no YAML dependency needed). The
literals in _DEFAULTS are only the fail-safe if the file is missing or unreadable. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import validate as contract  # sibling module; sys.path fix below for direct execution

# --- risk model, loaded from config/severity.yaml ------------------------------------------

_DEFAULTS = {
    "severity_weight": {"critical": 1.00, "high": 0.75, "medium": 0.50, "low": 0.25, "info": 0.05},
    "epss": {"default_when_unknown": 0.30,
             "category_priors": {"CWE-89": 0.70, "CWE-79": 0.60, "CWE-78": 0.70, "CWE-22": 0.55,
                                 "CWE-502": 0.65, "CWE-798": 0.60, "CWE-306": 0.55}},
    "environmental": {"reachable_from_entrypoint": 1.00, "reachable_internal_only": 0.60,
                      "reachability_unknown": 0.50, "unreachable_dead_code": 0.10},
    "non_security_scale": {"security": 1.00, "logic": 0.90, "supply-chain": 0.90,
                           "quality": 0.55, "testing": 0.55, "performance": 0.60,
                           "accessibility": 0.50},
    "confidence_gate": {"min_to_report": 0.55, "ground_truth_bypass": True,
                        "abstain_shown": False},
}

_KV_RE = re.compile(r"^(\s*)([\w.-]+):\s*(.*?)\s*$")


def _coerce(raw: str):
    raw = raw.split("  #")[0].split("\t#")[0].strip()
    if raw.endswith("#"):
        raw = raw[:-1].strip()
    low = raw.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return float(raw) if "." in raw else int(raw)
    except ValueError:
        return raw.strip("\"'")


def _load_flat_yaml(path: Path) -> dict:
    """Parse the strictly two/three-level `key: value` shape of severity.yaml. Not a general
    YAML parser — the eval pins the shape."""
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _KV_RE.match(line)
        if not m:
            continue
        indent, key, value = len(m.group(1)), m.group(2), m.group(3)
        # strip trailing inline comment on valued lines
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value == "" or value.startswith("#"):
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _coerce(value)
    return root


def _risk_model() -> dict:
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "severity.yaml"
    try:
        parsed = _load_flat_yaml(cfg_path)
    except Exception:
        return _DEFAULTS
    model = {}
    for section, default in _DEFAULTS.items():
        got = parsed.get(section)
        model[section] = got if isinstance(got, dict) and got else default
    # nested epss.category_priors fallback
    if not isinstance(model["epss"].get("category_priors"), dict):
        model["epss"]["category_priors"] = _DEFAULTS["epss"]["category_priors"]
    return model


_MODEL = _risk_model()
SEVERITY_WEIGHT = _MODEL["severity_weight"]
EPSS_DEFAULT = _MODEL["epss"].get("default_when_unknown", 0.30)
EPSS_CATEGORY_PRIORS = _MODEL["epss"]["category_priors"]
ENVIRONMENTAL = _MODEL["environmental"]
NON_SECURITY_SCALE = _MODEL["non_security_scale"]
MIN_TO_REPORT = _MODEL["confidence_gate"].get("min_to_report", 0.55)
GROUND_TRUTH_BYPASS = bool(_MODEL["confidence_gate"].get("ground_truth_bypass", True))
ABSTAIN_SHOWN = bool(_MODEL["confidence_gate"].get("abstain_shown", False))

SEC_ASPECTS = {"security", "supply-chain"}

# Findings for the same defect rarely land on the exact same line across tools (a scanner
# anchors the sink, the LLM the function head). Merge within this window.
DEDUP_LINE_WINDOW = 3


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


def _same_defect(a: dict, b: dict) -> bool:
    """Proximity dedup: same aspect + file, lines within DEDUP_LINE_WINDOW, and overlapping
    canonical IDs (or both ID-less). Exact-line matching under-merged scanner-vs-LLM duplicates
    that anchor one line apart."""
    if a.get("aspect") != b.get("aspect") or a.get("file", "") != b.get("file", ""):
        return False
    if abs((a.get("line") or 0) - (b.get("line") or 0)) > DEDUP_LINE_WINDOW:
        return False
    ca, cb = set(a.get("canonical_ids") or []), set(b.get("canonical_ids") or [])
    return bool(ca & cb) if (ca or cb) else True


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
    # Contract check at the seam: a drifting inspector must not corrupt the report.
    findings, invalid = contract.split_valid(findings)

    reportable = [f for f in findings if _reportable(f)]
    rejected = sum(1 for f in findings if f.get("status") == "rejected")
    abstained = sum(1 for f in findings if f.get("status") == "abstain")
    suppressed = sum(1 for f in findings if f.get("status") == "suppressed")

    # Proximity dedup: greedy grouping of same-defect findings (stable input order).
    groups: list[list[dict]] = []
    for f in sorted(reportable, key=lambda x: (x.get("file", ""), x.get("line") or 0)):
        for g in groups:
            if _same_defect(g[0], f):
                g.append(f)
                break
        else:
            groups.append([f])
    merged = [_merge(g) for g in groups]

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
            "effort": _effort(f),
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
            "invalid_count": len(invalid),
            "invalid": invalid,
        },
    }


def _effort(f: dict) -> str:
    """Rough effort estimate from the concreteness/size of the proposed fix — not hardcoded."""
    fix = f.get("proposed_fix") or ""
    if not fix:
        return "medium"  # no concrete patch: someone has to design the fix
    lines = [l for l in fix.splitlines() if l.strip()]
    if len(lines) <= 2:
        return "trivial"
    return "small" if len(lines) <= 15 else "medium"


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
    ap.add_argument("--baseline", default=None,
                    help="Path to a prior .behdad/last-run.json to compute a New/Fixed/Still-open delta")
    ap.add_argument("--scan", default=None,
                    help="Path to scan.json — if it was a scoped (--since) run, makes the delta scope-aware")
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

    # Incremental delta: compare the reported findings against a prior run's snapshot.
    if args.baseline:
        try:
            prev = json.loads(Path(args.baseline).read_text(encoding="utf-8")).get("findings", [])
            # If this was a scoped (--since) run, only files in scan.changed_files were re-checked.
            scope_files = None
            if args.scan:
                env = json.loads(Path(args.scan).read_text(encoding="utf-8"))
                if env.get("scoped"):
                    scope_files = env.get("changed_files", [])
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import runstate  # noqa: E402
            d = runstate.delta(prev, report["findings"], scope_files=scope_files)
            report["delta"] = {"counts": d["counts"], "new": d["new"], "fixed": d["fixed"]}
        except Exception as exc:
            report["delta"] = {"error": f"could not compute delta: {exc}"}

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
