"""
render_report.py — turn a Behdad report.json into a durable, human-readable Markdown report.

Saved into the audited project's own .behdad/ folder so there's a permanent record of what Behdad
found and recommended on each run — you can read it later, diff it, or commit it.

Writes:
  <target>/.behdad/report-<timestamp>.md   (the run's report)
  <target>/.behdad/report-latest.md        (always the most recent, for easy access)

Usage: python render_report.py <report.json> --target <project> [--timestamp 2026-07-01T13-16-00]
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

SEV_ORDER = ["critical", "high", "medium", "low", "info"]
SEV_LABEL = {"critical": "🔴 Critical", "high": "🟠 High", "medium": "🟡 Medium",
             "low": "⚪ Low", "info": "ℹ️ Info"}


def _md(report: dict, target: Path, stamp: str) -> str:
    L: list[str] = []
    summary = report.get("summary", {})
    scope = report.get("scope", {})
    meas = report.get("measurement", {})
    delta = report.get("delta")
    findings = report.get("findings", [])
    plan = report.get("action_plan", [])

    L.append(f"# Behdad audit report — {target.name}")
    tgt = report.get("target", {})
    commit = tgt.get("commit") or ""
    L.append(f"_{stamp}_ · depth: **{scope.get('depth', '?')}**"
             + (f" · commit `{commit[:12]}`" if commit else ""))
    L.append("")

    # Verdict
    L.append("## Verdict")
    L.append(summary.get("headline", "(no summary)"))
    cbs = summary.get("counts_by_severity", {})
    if cbs:
        L.append("")
        L.append(" · ".join(f"**{cbs[s]}** {s}" for s in SEV_ORDER if s in cbs))
    L.append("")

    # Performance / how it did
    if meas:
        L.append("## How this audit performed")
        raw = meas.get("raw_scanner_findings")
        rep = meas.get("reported_findings")
        if raw is not None:
            L.append(f"- **Noise control:** scanners raised **{raw}** raw findings; "
                     f"Behdad reported **{rep}** "
                     f"({meas.get('noise_reduction_pct', 0)}% filtered as noise, "
                     f"{meas.get('rejected_by_critic', 0)} rejected by the critic).")
        rem = meas.get("remediation")
        if rem:
            L.append(f"- **After fixes:** resolved **{rem.get('resolved', 0)}**, "
                     f"introduced **{rem.get('introduced', 0)}** new "
                     f"(tests: {rem.get('tests_before')} → {rem.get('tests_after')}).")
        L.append("")

    # Coverage
    L.append("## Coverage")
    langs = ", ".join(scope.get("languages", []) or []) or "—"
    L.append(f"- Languages: {langs}")
    if scope.get("aspects_run"):
        L.append(f"- Aspects run: {', '.join(scope['aspects_run'])}")
    if scope.get("aspects_skipped"):
        sk = "; ".join(f"{a.get('aspect')} ({a.get('reason')})" for a in scope["aspects_skipped"])
        L.append(f"- Aspects skipped: {sk}")
    if scope.get("tools_used"):
        L.append(f"- Tools used: {', '.join(scope['tools_used'])}")
    if scope.get("tools_missing"):
        miss = ", ".join(m.get("id", str(m)) if isinstance(m, dict) else str(m)
                         for m in scope["tools_missing"])
        L.append(f"- ⚠️ Tools missing (reduced recall): {miss}")
    L.append("")

    # Delta (incremental runs)
    if delta and delta.get("counts"):
        c = delta["counts"]
        L.append("## Change since last run")
        L.append(f"- 🆕 New: **{c.get('new', 0)}** · ✅ Fixed: **{c.get('fixed', 0)}** · "
                 f"➖ Still open: **{c.get('still_open', 0)}**")
        for f in delta.get("new", [])[:20]:
            L.append(f"  - 🆕 {f.get('severity','?')} — {f.get('title', f.get('file',''))}")
        for f in delta.get("fixed", [])[:20]:
            L.append(f"  - ✅ fixed — {f.get('title', f.get('file',''))}")
        L.append("")

    # Action plan
    if plan:
        L.append("## Prioritized action plan")
        L.append("")
        L.append("| # | Severity | Action | Auto-fix? |")
        L.append("|---|----------|--------|-----------|")
        fmap = {f.get("id"): f for f in findings}
        for a in plan:
            f = fmap.get(a.get("finding_id"), {})
            sev = f.get("severity", "?")
            act = (a.get("action", "") or "").replace("|", "\\|")[:140]
            L.append(f"| {a.get('order')} | {sev} | {act} | "
                     f"{'✅' if a.get('auto_fixable') else '—'} |")
        L.append("")

    # Detailed findings, grouped by severity
    if findings:
        L.append("## Findings in detail")
        by_sev: dict[str, list] = {}
        for f in findings:
            by_sev.setdefault(f.get("severity", "info"), []).append(f)
        for sev in SEV_ORDER:
            group = by_sev.get(sev)
            if not group:
                continue
            L.append("")
            L.append(f"### {SEV_LABEL.get(sev, sev)}")
            for f in group:
                ids = " · ".join(f.get("canonical_ids", []) or [])
                loc = f"{f.get('file','')}:{f.get('line',0)}"
                L.append("")
                L.append(f"#### {f.get('title', '(untitled)')}")
                L.append(f"`{loc}`" + (f" — {ids}" if ids else "")
                         + f" · aspect: {f.get('aspect','?')}"
                         + f" · confidence: {f.get('confidence','?')}")
                if f.get("explanation_for_humans"):
                    L.append(f"- **Why it matters:** {f['explanation_for_humans']}")
                if f.get("evidence"):
                    L.append(f"- **Evidence:** {f['evidence']}")
                if f.get("proposed_fix"):
                    L.append("- **Proposed fix:**")
                    L.append("  ```diff")
                    for line in str(f["proposed_fix"]).splitlines():
                        L.append("  " + line)
                    L.append("  ```")
        L.append("")

    at = report.get("audit_trail", {})
    L.append("---")
    L.append(f"_Generated by Better-call-behdad · rejected {at.get('rejected_count',0)}, "
             f"abstained {at.get('abstained_count',0)}, suppressed {at.get('suppressed_count',0)}._")
    return "\n".join(L) + "\n"


def render(report: dict, target: Path, stamp: str | None = None) -> Path:
    stamp = stamp or time.strftime("%Y-%m-%dT%H-%M-%S")
    out_dir = target / ".behdad"
    out_dir.mkdir(exist_ok=True)
    md = _md(report, target, stamp)
    dated = out_dir / f"report-{stamp}.md"
    dated.write_text(md, encoding="utf-8", newline="\n")
    (out_dir / "report-latest.md").write_text(md, encoding="utf-8", newline="\n")
    return dated


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render a Behdad report.json to Markdown in .behdad/")
    ap.add_argument("report")
    ap.add_argument("--target", required=True)
    ap.add_argument("--timestamp", default=None)
    args = ap.parse_args(argv)

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    target = Path(args.target).resolve()
    path = render(report, target, args.timestamp)
    print(f"saved report -> {path}")
    print(f"           -> {target / '.behdad' / 'report-latest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
