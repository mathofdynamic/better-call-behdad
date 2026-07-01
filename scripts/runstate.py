"""
runstate.py — Behdad's memory of its last run on a project.

Persists a small snapshot to <target>/.behdad/last-run.json after each audit: the git commit it
saw, when, and a minimal fingerprint of the findings. The next run uses this to (a) scope the scan
to files changed since then (`--since last-run`) and (b) produce a New / Fixed / Still-open delta.
Stdlib only.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path


def _state_path(target: Path) -> Path:
    return target / ".behdad" / "last-run.json"


def git_head(target: Path) -> str:
    try:
        p = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=15)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def load(target: Path) -> dict | None:
    p = _state_path(target)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def last_commit(target: Path) -> str:
    st = load(target)
    return (st or {}).get("git_commit", "") if st else ""


def _fingerprint(f: dict) -> dict:
    return {
        "id": f.get("id", ""),
        "aspect": f.get("aspect", ""),
        "canonical_ids": sorted(f.get("canonical_ids") or []),
        "file": (f.get("file") or "").replace("\\", "/"),
        "title": f.get("title", ""),
        "severity": f.get("severity", ""),
    }


def save(target: Path, findings: list[dict], depth: str = "quick", commit: str | None = None) -> dict:
    """Write the run snapshot. Returns it. `findings` = the reported (verified) findings."""
    state = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "git_commit": commit if commit is not None else git_head(target),
        "depth": depth,
        "target": str(target),
        "findings": [_fingerprint(f) for f in findings],
    }
    p = _state_path(target)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def _main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Save Behdad's run state for a target project")
    ap.add_argument("--target", required=True)
    ap.add_argument("--report", required=True, help="reports/report.json from this run")
    ap.add_argument("--depth", default="quick")
    args = ap.parse_args(argv)
    target = Path(args.target).resolve()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    st = save(target, report.get("findings", []), depth=args.depth)
    print(f"saved run state -> {_state_path(target)} "
          f"(commit {st['git_commit'][:12] or 'n/a'}, {len(st['findings'])} findings)")
    return 0


def _file_of(f: dict) -> str:
    return (f.get("file") or "").replace("\\", "/")


def delta(previous: list[dict], current: list[dict], scope_files: list[str] | None = None) -> dict:
    """
    Compare two finding sets by a line-independent key (aspect+canonical_ids+file+title) so edits
    above a finding don't make it look 'new'. Returns New / Fixed / Still-open buckets.

    SCOPE-AWARE: in an incremental (scoped) run only `scope_files` were re-scanned, so findings in
    OTHER files can't be judged fixed — they're 'carried_over' (assumed still present), and only
    findings inside the scope are compared for new/fixed. Pass scope_files=None for a full run.
    """
    def key(f: dict) -> str:
        fp = f if "title" in f and "aspect" in f else _fingerprint(f)
        return f"{fp['aspect']}|{','.join(fp.get('canonical_ids') or [])}|{fp['file']}|{fp['title']}"

    carried: list[dict] = []
    if scope_files is not None:
        scope = {p.replace("\\", "/") for p in scope_files}
        carried = [f for f in previous if _file_of(f) not in scope]
        previous = [f for f in previous if _file_of(f) in scope]

    prev = {key(f): f for f in previous}
    curr = {key(f): f for f in current}
    new = [curr[k] for k in curr if k not in prev]
    fixed = [prev[k] for k in prev if k not in curr]
    still = [curr[k] for k in curr if k in prev]
    return {
        "new": new, "fixed": fixed, "still_open": still, "carried_over": carried,
        "counts": {"new": len(new), "fixed": len(fixed),
                   "still_open": len(still), "carried_over": len(carried)},
    }


if __name__ == "__main__":
    raise SystemExit(_main())
