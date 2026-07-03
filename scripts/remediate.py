"""
remediate.py — Behdad's staged, reversible fix applier.

Runs ONLY after the user has approved the action report. For each approved fix it:
  1. backs up every file the patch touches (snapshot rollback that works with or without git),
  2. applies the unified diff (via `git apply`, which works inside or outside a git repo),
  3. runs the verification command (tests / scanners),
  4. rolls back automatically if verification fails or the patch doesn't apply,
and reports the outcome HONESTLY — a broken fix is reported as rolled-back, never as success.

Safety: the target repo is treated as untrusted for its CONTENT, but the patch and verify command
come from Behdad/the user post-approval. Patches are applied with git apply (no shell); the verify
command is the user's own and is run as given.

Usage:
  python remediate.py --target <repo> --patch fix.diff --verify "pytest -q" [--id CWE-89@app.py:18]
Stdlib only (uses the `git` binary if present for apply; falls back to error if absent).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_DIFF_PATH_RE = re.compile(r"^\+\+\+ [ab]/(.+?)\s*$", re.MULTILINE)
_DIFF_PATH_RE2 = re.compile(r"^--- [ab]/(.+?)\s*$", re.MULTILINE)


def patched_files(patch_text: str) -> list[str]:
    files = set(_DIFF_PATH_RE.findall(patch_text)) | set(_DIFF_PATH_RE2.findall(patch_text))
    return sorted(f for f in files if f and f != "/dev/null")


def _git_available() -> bool:
    return shutil.which("git") is not None


def _backup(target: Path, files: list[str], backup_dir: Path) -> dict[str, str]:
    """Copy each existing target file into backup_dir; record which existed."""
    saved: dict[str, str] = {}
    for rel in files:
        src = target / rel
        if src.exists():
            dst = backup_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            saved[rel] = "existed"
        else:
            saved[rel] = "new"  # created by the patch; rollback = delete
    return saved


def _restore(target: Path, saved: dict[str, str], backup_dir: Path) -> None:
    for rel, state in saved.items():
        dst = target / rel
        if state == "existed":
            shutil.copy2(backup_dir / rel, dst)
        else:  # was newly created by the patch
            if dst.exists():
                dst.unlink()


def _run(cmd, *, cwd=None, timeout=600, shell=False):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, shell=shell)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout after {timeout}s"
    except Exception as exc:  # pragma: no cover
        return -2, "", str(exc)


def apply_fix(target: Path, patch_text: str, verify: str | None, *, timeout: int) -> dict:
    files = patched_files(patch_text)
    if not files:
        return {"applied": False, "verified": False, "rolled_back": False,
                "error": "could not parse any target files from the patch"}
    if not _git_available():
        return {"applied": False, "verified": False, "rolled_back": False,
                "error": "git not found on PATH — needed to apply patches. Install git or apply manually."}

    with tempfile.TemporaryDirectory(prefix="behdad_backup_") as tmp:
        backup_dir = Path(tmp)
        saved = _backup(target, files, backup_dir)

        # Write patch to a temp file and apply with git apply (works in/out of a repo).
        # IMPORTANT: preserve LF newlines. On Windows, text mode would rewrite \n -> \r\n and
        # git apply would then reject the patch as "does not apply" against LF sources.
        patch_file = backup_dir / "fix.diff"
        patch_file.write_text(patch_text, encoding="utf-8", newline="\n")
        rc, out, err = _run(
            ["git", "apply", "--whitespace=nowarn", "-p1", str(patch_file)],
            cwd=str(target),
        )
        if rc != 0:
            return {"applied": False, "verified": False, "rolled_back": False,
                    "files": files, "error": f"git apply failed: {err.strip()[:400]}"}

        # Verify. If no command was given, try to auto-detect the project's test runner —
        # an unverified fix must be reported as UNVERIFIED, never allowed to read as success.
        if not verify:
            verify = _detect_verify(target)
        if not verify:
            return {"applied": True, "verified": None, "rolled_back": False, "files": files,
                    "status": "UNVERIFIED",
                    "note": "UNVERIFIED: no --verify command given and no test runner detected "
                            "(pytest/npm test/cargo test/go test). Review this change manually."}

        vrc, vout, verr = _run(verify, cwd=str(target), shell=True, timeout=timeout)
        if vrc == 0:
            return {"applied": True, "verified": True, "rolled_back": False, "files": files,
                    "verify_rc": vrc}
        # Verification failed -> roll back.
        _restore(target, saved, backup_dir)
        return {"applied": True, "verified": False, "rolled_back": True, "files": files,
                "verify_rc": vrc,
                "verify_output": (vout + "\n" + verr)[-800:].strip(),
                "note": "verification failed; changes were rolled back"}


def _detect_verify(target: Path) -> str | None:
    """Best-effort test-runner detection (presence probes only — no execution here)."""
    import shutil as _sh
    if (any((target / d).is_dir() and any(p.name.startswith("test") for p in (target / d).glob("*.py"))
            for d in ("tests", "test")) and _sh.which("pytest")):
        return "pytest -q"
    pkg = target / "package.json"
    if pkg.exists() and _sh.which("npm"):
        try:
            if "test" in (json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}):
                return "npm test --silent"
        except Exception:
            pass
    if (target / "Cargo.toml").exists() and _sh.which("cargo"):
        return "cargo test --quiet"
    if (target / "go.mod").exists() and _sh.which("go"):
        return "go test ./..."
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Behdad staged fix applier")
    ap.add_argument("--target", required=True)
    ap.add_argument("--patch", required=True, help="Unified diff file to apply")
    ap.add_argument("--verify", default=None, help="Verification command, e.g. 'pytest -q'")
    ap.add_argument("--id", default="", help="Finding id this fix addresses (for the log)")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args(argv)

    target = Path(args.target).resolve()
    if not target.exists():
        print(json.dumps({"error": f"target not found: {target}"})); return 2

    patch_text = Path(args.patch).read_text(encoding="utf-8")
    result = apply_fix(target, patch_text, args.verify, timeout=args.timeout)
    result["finding_id"] = args.id
    result["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    # Append to the target's audit trail.
    trail_dir = target / ".behdad"
    trail_dir.mkdir(exist_ok=True)
    with (trail_dir / "remediation.log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result) + "\n")

    print(json.dumps(result, indent=2))
    # Exit non-zero if a fix failed to apply or was rolled back, so callers can react.
    return 0 if result.get("verified") in (True, None) and not result.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
