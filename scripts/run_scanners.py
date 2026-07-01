"""
run_scanners.py — Behdad's deterministic ground-truth layer.

Detects the languages/manifests in a target project, runs whichever supported scanners are
installed (headlessly, with per-tool timeouts), normalizes every result into one finding
stream, and emits a JSON envelope the manager/inspectors consume.

SAFETY (prompt-injection hardening, per the plan):
  * Commands are built as ARGUMENT LISTS and run WITHOUT shell=True — a malicious file path
    or repo name can never break out into a shell.
  * Code-executing tools (type-checkers, test runners) are OFF by default; a plain scan never
    runs arbitrary target code.
  * Missing tools are reported loudly (reduced-recall caveat), never silently skipped.

Usage:
  python run_scanners.py <target_dir> [--depth quick|thorough] [--out findings.json]
                                      [--allow-code-execution] [--timeout 180]

Output envelope:
  { target, depth, languages, tools_used, tools_missing, findings: [...], errors: [...] }
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sarif_normalize as norm  # noqa: E402
import tool_registry as reg  # noqa: E402

# Directories never scanned (mirror config/fp-exclusions.yaml exclude_paths).
PRUNE_DIRS = {
    "node_modules", ".venv", "venv", "dist", "build", "vendor",
    "__pycache__", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache",
}

EXT_LANG = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".go": "go", ".java": "java", ".rb": "ruby", ".php": "php",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".rs": "rust",
}

MANIFESTS = {
    "requirements.txt", "pyproject.toml", "poetry.lock", "pipfile.lock",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "go.mod", "go.sum", "cargo.toml", "cargo.lock", "gemfile.lock", "composer.lock",
}


def detect_languages(target: Path) -> tuple[set[str], bool]:
    """Walk the tree (pruning vendored/generated dirs); return (languages, has_manifest)."""
    langs: set[str] = set()
    has_manifest = False
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in PRUNE_DIRS]
        for f in files:
            ext = Path(f).suffix.lower()
            if ext in EXT_LANG:
                langs.add(EXT_LANG[ext])
            if f.lower() in MANIFESTS:
                has_manifest = True
    return langs, has_manifest


def _run(cmd: list[str], *, timeout: int, cwd: str | None = None) -> tuple[int, str, str]:
    """Run a command safely (no shell). Returns (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd,
            shell=False,  # explicit: never interpret args through a shell
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout after {timeout}s"
    except FileNotFoundError:
        return -2, "", "binary not found"
    except Exception as exc:  # pragma: no cover - defensive
        return -3, "", str(exc)


def _parse(stdout: str):
    stdout = stdout.strip()
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def build_command(tool_id: str, target: str, tmpdir: str) -> tuple[list[str], str | None]:
    """
    Return (argv, out_file). If out_file is not None, the tool writes there and we read it;
    otherwise we read the tool's stdout. Note: many scanners exit non-zero when they FIND
    issues — that is success, not failure, and is handled by the caller.
    """
    if tool_id == "semgrep":
        return (["semgrep", "scan", "--sarif", "--config", "auto", "--quiet",
                 "--metrics", "off", target], None)
    if tool_id == "bandit":
        return (["bandit", "-r", "-f", "json", "-q", target], None)
    if tool_id == "ruff":
        return (["ruff", "check", target, "--output-format", "json", "--quiet"], None)
    if tool_id == "eslint":
        return (["eslint", target, "-f", "json"], None)
    if tool_id == "gitleaks":
        out = os.path.join(tmpdir, "gitleaks.json")
        return (["gitleaks", "detect", "--source", target, "--no-git",
                 "--report-format", "json", "--report-path", out,
                 "--exit-code", "0", "--no-banner"], out)
    if tool_id == "osv-scanner":
        return (["osv-scanner", "--format", "json", "-r", target], None)
    if tool_id == "trivy":
        return (["trivy", "fs", "--format", "sarif", "--quiet", target], None)
    raise ValueError(f"no command builder for {tool_id}")


def scan(target: Path, *, depth: str, timeout: int, allow_code_execution: bool) -> dict:
    langs, has_manifest = detect_languages(target)
    allow_slow = depth == "thorough"
    installed = reg.available_tools(
        allow_code_execution=allow_code_execution, allow_slow=allow_slow
    )
    installed_ids = {t.id for t in installed}

    # Decide which installed tools are RELEVANT to this repo (scope routing = cost governor).
    relevant: list[str] = []
    if langs:
        relevant.append("semgrep")           # broad SAST across languages
    if "python" in langs:
        relevant += ["bandit", "ruff"]
    if {"javascript", "typescript"} & langs:
        relevant.append("eslint")
    relevant.append("gitleaks")              # secrets can hide anywhere
    if has_manifest:
        relevant += ["osv-scanner", "trivy"]

    to_run = [t for t in dict.fromkeys(relevant) if t in installed_ids]
    # Everything relevant but not installed -> loud missing report.
    missing = reg.missing_report([t for t in dict.fromkeys(relevant)])

    findings: list[dict] = []
    errors: list[dict] = []
    tools_used: list[str] = []

    with tempfile.TemporaryDirectory(prefix="behdad_scan_") as tmpdir:
        for tool_id in to_run:
            argv, out_file = build_command(tool_id, str(target), tmpdir)
            rc, out, err = _run(argv, timeout=timeout)
            if rc in (-1, -2, -3):  # infra failure (timeout / missing / crash), not "found issues"
                errors.append({"tool": tool_id, "error": err or f"rc={rc}"})
                continue
            # Read result: from file or stdout.
            if out_file:
                try:
                    doc = json.loads(Path(out_file).read_text(encoding="utf-8"))
                except Exception as exc:
                    errors.append({"tool": tool_id, "error": f"unreadable report: {exc}"})
                    continue
            else:
                doc = _parse(out)
                if doc is None:
                    # No parseable output. If stderr looks like a real error, record it.
                    if err.strip():
                        errors.append({"tool": tool_id, "error": err.strip()[:500]})
                    continue
            raw = norm.normalize(tool_id, doc)
            findings.extend(raw)
            tools_used.append(tool_id)

    return {
        "target": str(target),
        "depth": depth,
        "languages": sorted(langs),
        "has_manifest": has_manifest,
        "tools_used": tools_used,
        "tools_missing": missing,
        "findings": findings,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Behdad deterministic scanner layer")
    ap.add_argument("target", help="Path to the project to scan")
    ap.add_argument("--depth", choices=["quick", "thorough"], default="quick")
    ap.add_argument("--out", help="Write envelope JSON here (default: stdout)")
    ap.add_argument("--timeout", type=int, default=180, help="Per-tool timeout in seconds")
    ap.add_argument("--allow-code-execution", action="store_true",
                    help="Permit type-checkers/test-runners that import target code (unsafe on untrusted repos)")
    args = ap.parse_args(argv)

    target = Path(args.target).resolve()
    if not target.exists():
        print(json.dumps({"error": f"target not found: {target}"}), file=sys.stderr)
        return 2

    envelope = scan(
        target, depth=args.depth, timeout=args.timeout,
        allow_code_execution=args.allow_code_execution,
    )
    text = json.dumps(envelope, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {len(envelope['findings'])} raw findings to {args.out} "
              f"(tools: {', '.join(envelope['tools_used']) or 'none'}; "
              f"missing: {len(envelope['tools_missing'])})")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
