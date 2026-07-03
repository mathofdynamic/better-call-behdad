"""
run_scanners.py — Behdad's deterministic ground-truth layer.

Detects the languages/manifests in a target project, runs whichever supported scanners are
installed (headlessly, with per-tool timeouts), normalizes every result into one finding stream,
and emits a JSON envelope the manager/inspectors consume.

INCREMENTAL MODE (--since): scope the scan to files changed since a git ref (or `last-run`, read
from .behdad/last-run.json). Per-file tools (semgrep/bandit/ruff/eslint) run only on the changed
files; secrets (gitleaks) still sweep the whole tree (a secret can be introduced anywhere and it's
cheap); dependency tools (osv/trivy) run only if a manifest changed. This makes re-audits fast.

SAFETY (prompt-injection hardening, per the plan):
  * Commands are ARGUMENT LISTS run WITHOUT shell=True — a malicious path can't break into a shell.
  * Code-executing tools (type-checkers, test runners) are OFF by default.
  * Missing tools are reported loudly (reduced-recall caveat), never silently skipped.

Usage:
  python run_scanners.py <target_dir> [--depth quick|thorough] [--since <ref>|last-run]
                                      [--out findings.json] [--allow-code-execution] [--timeout 180]
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
import runstate  # noqa: E402
import sarif_normalize as norm  # noqa: E402
import tool_registry as reg  # noqa: E402

PRUNE_DIRS = {
    "node_modules", ".venv", "venv", "dist", "build", "vendor",
    "__pycache__", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    ".behdad",  # Behdad's own control/report dir — never audit it
}


def _relpath(fp: str, target: Path) -> str:
    """Normalize a scanner-reported path to repo-relative with forward slashes, so findings from
    full scans (relative) and scoped scans (absolute file args) compare consistently, and match
    git's relative changed-file list."""
    if not fp:
        return fp
    p = Path(fp)
    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(target)).replace("\\", "/")
        except Exception:
            return fp.replace("\\", "/")
    return fp.replace("\\", "/")

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

PY_EXT = {".py"}
JS_EXT = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}


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


def changed_files_since(target: Path, ref: str) -> tuple[list[str], str | None]:
    """
    Repo-relative paths that differ from `ref` (committed diff vs working tree) plus untracked
    files. Returns (files, error). error is a message if git/ref is unusable (caller falls back
    to a full scan).
    """
    def _git(args: list[str]) -> tuple[int, str]:
        try:
            p = subprocess.run(["git", "-C", str(target), *args],
                               capture_output=True, text=True, timeout=30)
            return p.returncode, p.stdout
        except Exception as exc:  # pragma: no cover
            return -1, str(exc)

    rc, _ = _git(["rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        return [], "target is not a git repository"
    rc, _ = _git(["rev-parse", "--verify", "--quiet", ref])
    if rc != 0:
        return [], f"git ref '{ref}' not found"
    changed: set[str] = set()
    rc, out = _git(["diff", "--name-only", ref])            # ref vs working tree (tracked)
    if rc == 0:
        changed.update(l.strip() for l in out.splitlines() if l.strip())
    rc, out = _git(["ls-files", "--others", "--exclude-standard"])  # untracked
    if rc == 0:
        changed.update(l.strip() for l in out.splitlines() if l.strip())
    # Keep only files that still exist and aren't in pruned dirs.
    files = []
    for rel in sorted(changed):
        p = target / rel
        if p.is_file() and not any(part in PRUNE_DIRS for part in Path(rel).parts):
            files.append(rel)
    return files, None


def _langs_of(files: list[str]) -> tuple[set[str], bool]:
    langs: set[str] = set()
    has_manifest = False
    for rel in files:
        ext = Path(rel).suffix.lower()
        if ext in EXT_LANG:
            langs.add(EXT_LANG[ext])
        if Path(rel).name.lower() in MANIFESTS:
            has_manifest = True
    return langs, has_manifest


def _filter_ext(files: list[str], exts: set[str], target: Path) -> list[str]:
    return [str(target / f) for f in files if Path(f).suffix.lower() in exts]


def _run(cmd: list[str], *, timeout: int, cwd: str | None = None) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                           shell=False)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout after {timeout}s"
    except FileNotFoundError:
        return -2, "", "binary not found"
    except Exception as exc:  # pragma: no cover
        return -3, "", str(exc)


def _parse(stdout: str):
    stdout = stdout.strip()
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


# Language-specific semgrep registry packs layered on top of p/default: the generic pack is
# thin outside Python/JS, so each detected language pulls in its dedicated ruleset.
SEMGREP_LANG_PACKS = {
    "python": "p/python",
    "javascript": "p/javascript", "typescript": "p/javascript",
    "go": "p/golang", "java": "p/java", "ruby": "p/ruby", "php": "p/php",
}


def build_command(tool_id: str, target: str, tmpdir: str, paths: list[str] | None,
                  langs: set[str] | None = None):
    """
    Return (argv, out_file). `paths` is the scoped file list for per-file tools; None = whole dir.
    Many scanners exit non-zero when they FIND issues — that's success, handled by the caller.
    """
    if tool_id == "semgrep":
        # Use named rulesets, NOT '--config auto': auto REQUIRES metrics to be on (telemetry),
        # which we refuse for a tool auditing private code. Named packs work with metrics off
        # and are fetched from the registry once, then cached.
        tgts = paths if paths else [target]
        configs = ["--config", "p/default"]
        for lang in sorted(langs or set()):
            pack = SEMGREP_LANG_PACKS.get(lang)
            if pack and pack not in configs:
                configs += ["--config", pack]
        # --no-git-ignore: in a git repo semgrep defaults to TRACKED files only, silently
        # skipping uncommitted code — exactly the code an audit most needs to see.
        return (["semgrep", "scan", "--sarif", *configs, "--quiet", "--no-git-ignore",
                 "--metrics", "off", *tgts], None)
    if tool_id == "bandit":
        if paths:
            return (["bandit", "-f", "json", "-q", *paths], None)
        return (["bandit", "-r", "-f", "json", "-q", target], None)
    if tool_id == "ruff":
        tgts = paths if paths else [target]
        return (["ruff", "check", *tgts, "--output-format", "json", "--quiet"], None)
    if tool_id == "eslint":
        tgts = paths if paths else [target]
        return (["eslint", *tgts, "-f", "json"], None)
    if tool_id == "gitleaks":  # always whole tree
        out = os.path.join(tmpdir, "gitleaks.json")
        return (["gitleaks", "detect", "--source", target, "--no-git",
                 "--report-format", "json", "--report-path", out,
                 "--exit-code", "0", "--no-banner"], out)
    if tool_id == "osv-scanner":
        return (["osv-scanner", "--format", "json", "-r", target], None)
    if tool_id == "trivy":
        return (["trivy", "fs", "--format", "sarif", "--quiet", target], None)
    if tool_id == "gosec":
        # ./... from the target dir; -quiet suppresses the banner; exit!=0 on findings is fine.
        return (["gosec", "-fmt=json", "-quiet", "./..."], None)
    if tool_id == "mypy":
        # Text output (parsed by from_mypy_text): mypy's JSON output only exists on newer
        # versions. --ignore-missing-imports keeps untyped third-party imports quiet.
        tgts = paths if paths else [target]
        return (["mypy", "--ignore-missing-imports", "--no-error-summary",
                 "--no-color-output", *tgts], None)
    raise ValueError(f"no command builder for {tool_id}")


# --- stdlib complexity pass (quality inspector's deterministic backstop) --------------------

_BRANCH_NODES = ("If", "For", "While", "ExceptHandler", "With", "Assert",
                 "BoolOp", "IfExp", "comprehension")

COMPLEXITY_WARN = 10   # McCabe > 10 -> medium (matches config/inspectors.yaml)
COMPLEXITY_HIGH = 15   # McCabe > 15 -> high


def _cyclomatic(func_node) -> int:
    """McCabe-ish cyclomatic complexity: 1 + branch points. BoolOp counts n-1 short-circuits."""
    import ast
    score = 1
    for node in ast.walk(func_node):
        name = type(node).__name__
        if name == "BoolOp":
            score += max(0, len(node.values) - 1)
        elif name in _BRANCH_NODES:
            score += 1
    return score


def complexity_findings(target: Path, paths: list[str] | None) -> list[dict]:
    """Flag functions whose cyclomatic complexity crosses the configured thresholds.
    Python-only (stdlib ast); other languages have no complexity backstop yet."""
    import ast
    files: list[Path]
    if paths:
        files = [Path(p) for p in paths if p.endswith(".py")]
    else:
        files = []
        for root, dirs, names in os.walk(target):
            dirs[:] = [d for d in dirs if d not in PRUNE_DIRS]
            files += [Path(root) / n for n in names if n.endswith(".py")]
    out: list[dict] = []
    for fp in files:
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if type(node).__name__ not in ("FunctionDef", "AsyncFunctionDef"):
                continue
            cc = _cyclomatic(node)
            if cc <= COMPLEXITY_WARN:
                continue
            sev = "high" if cc > COMPLEXITY_HIGH else "medium"
            out.append({
                "source": "complexity", "rule_id": "cyclomatic-complexity",
                "canonical_ids": [], "severity": sev,
                "file": str(fp), "line": node.lineno,
                "message": f"function '{node.name}' has cyclomatic complexity {cc} "
                           f"(warn > {COMPLEXITY_WARN}, high > {COMPLEXITY_HIGH})",
                "ground_truth": True, "status": "candidate",
            })
    return out


def scan(target: Path, *, depth: str, timeout: int, allow_code_execution: bool,
         since: str | None = None) -> dict:
    scoped = False
    changed_files: list[str] = []
    scope_note = ""

    if since:
        ref = runstate.last_commit(target) if since == "last-run" else since
        if since == "last-run" and not ref:
            scope_note = "no prior Behdad run recorded (.behdad/last-run.json); ran a FULL scan"
        else:
            files, err = changed_files_since(target, ref)
            if err:
                scope_note = f"--since fell back to full scan: {err}"
            elif not files:
                # Nothing changed — return an empty, honest envelope.
                return {"target": str(target), "depth": depth, "languages": [],
                        "has_manifest": False, "tools_used": [], "tools_missing": [],
                        "findings": [], "errors": [], "scoped": True, "since_ref": ref,
                        "changed_files": [], "scope_note": f"no files changed since {ref[:12]}"}
            else:
                scoped = True
                changed_files = files
                scope_note = f"scoped to {len(files)} file(s) changed since {ref[:12]}"

    if scoped:
        langs, has_manifest = _langs_of(changed_files)
    else:
        langs, has_manifest = detect_languages(target)

    allow_slow = depth == "thorough"
    installed = reg.available_tools(allow_code_execution=allow_code_execution, allow_slow=allow_slow)
    installed_ids = {t.id for t in installed}

    relevant: list[str] = []
    if langs:
        relevant.append("semgrep")
    if "python" in langs:
        relevant += ["bandit", "ruff", "mypy"]
    if {"javascript", "typescript"} & langs:
        relevant.append("eslint")
    if "go" in langs:
        relevant.append("gosec")
    relevant.append("gitleaks")
    if has_manifest:
        relevant += ["osv-scanner", "trivy"]

    to_run = [t for t in dict.fromkeys(relevant) if t in installed_ids]
    missing = reg.missing_report([t for t in dict.fromkeys(relevant)])

    # Per-tool scoped path lists (None = whole dir).
    def paths_for(tool_id: str) -> list[str] | None:
        if not scoped:
            return None
        if tool_id in ("bandit", "ruff", "mypy"):
            return _filter_ext(changed_files, PY_EXT, target)
        if tool_id == "eslint":
            return _filter_ext(changed_files, JS_EXT, target)
        if tool_id == "semgrep":
            return [str(target / f) for f in changed_files
                    if Path(f).suffix.lower() in EXT_LANG]
        return None  # gitleaks/osv/trivy: whole tree

    findings: list[dict] = []
    errors: list[dict] = []
    tools_used: list[str] = []

    with tempfile.TemporaryDirectory(prefix="behdad_scan_") as tmpdir:
        for tool_id in to_run:
            scoped_paths = paths_for(tool_id)
            if scoped and scoped_paths is not None and not scoped_paths:
                continue  # scoped run, but no changed file matches this tool's languages
            argv, out_file = build_command(tool_id, str(target), tmpdir, scoped_paths, langs)
            # gosec's ./... target is relative, so it must run from the target dir.
            rc, out, err = _run(argv, timeout=timeout,
                                cwd=str(target) if tool_id == "gosec" else None)
            if rc in (-1, -2, -3):
                errors.append({"tool": tool_id, "error": err or f"rc={rc}"})
                continue
            if tool_id == "mypy":  # text output, not JSON
                raw = norm.from_mypy_text(out)
                for f in raw:
                    f["file"] = _relpath(f.get("file", ""), target)
                findings.extend(raw)
                tools_used.append(tool_id)
                continue
            if out_file:
                try:
                    doc = json.loads(Path(out_file).read_text(encoding="utf-8"))
                except Exception as exc:
                    errors.append({"tool": tool_id, "error": f"unreadable report: {exc}"})
                    continue
            else:
                doc = _parse(out)
                if doc is None:
                    if err.strip():
                        errors.append({"tool": tool_id, "error": err.strip()[:500]})
                    continue
            raw = norm.normalize(tool_id, doc)
            for f in raw:  # normalize paths to repo-relative for consistent dedup/delta
                f["file"] = _relpath(f.get("file", ""), target)
            findings.extend(raw)
            tools_used.append(tool_id)

    # Deterministic complexity backstop for the quality inspector (stdlib, Python files only).
    if "python" in langs:
        cx = complexity_findings(target, paths_for("bandit"))
        for f in cx:
            f["file"] = _relpath(f.get("file", ""), target)
        if cx:
            findings.extend(cx)
        tools_used.append("complexity")

    return {
        "target": str(target),
        "depth": depth,
        "languages": sorted(langs),
        "has_manifest": has_manifest,
        "tools_used": tools_used,
        "tools_missing": missing,
        "findings": findings,
        "errors": errors,
        "scoped": scoped,
        "since_ref": (runstate.last_commit(target) if since == "last-run" else since) if since else None,
        "changed_files": changed_files,
        "scope_note": scope_note,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Behdad deterministic scanner layer")
    ap.add_argument("target", help="Path to the project to scan")
    ap.add_argument("--depth", choices=["quick", "thorough"], default="quick")
    ap.add_argument("--since", default=None,
                    help="Scope to files changed since a git ref, or 'last-run' to use the last audit's commit")
    ap.add_argument("--out", help="Write envelope JSON here (default: stdout)")
    ap.add_argument("--timeout", type=int, default=180, help="Per-tool timeout in seconds")
    ap.add_argument("--allow-code-execution", action="store_true",
                    help="Permit type-checkers/test-runners that import target code (unsafe on untrusted repos)")
    args = ap.parse_args(argv)

    target = Path(args.target).resolve()
    if not target.exists():
        print(json.dumps({"error": f"target not found: {target}"}), file=sys.stderr)
        return 2

    envelope = scan(target, depth=args.depth, timeout=args.timeout,
                    allow_code_execution=args.allow_code_execution, since=args.since)
    text = json.dumps(envelope, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        note = f" | {envelope.get('scope_note')}" if envelope.get("scope_note") else ""
        print(f"wrote {len(envelope['findings'])} raw findings to {args.out} "
              f"(tools: {', '.join(envelope['tools_used']) or 'none'}; "
              f"missing: {len(envelope['tools_missing'])}){note}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
