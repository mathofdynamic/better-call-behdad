"""
install.py — install Better-call-behdad into Claude Code (user-level ~/.claude).

Copies the skill, registers the inspector/critic subagents and the /behdad command, and merges the
PreToolUse fix-gate hook into settings.json (backing it up first, preserving everything else).
Idempotent: safe to re-run to update. Stdlib only.

  python platform/claude/install.py            # install / update
  python platform/claude/install.py --uninstall
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOME = Path.home() / ".claude"
SKILL_DST = HOME / "skills" / "better-call-behdad"
AGENTS_DST = HOME / "agents"
COMMANDS_DST = HOME / "commands"
SETTINGS = HOME / "settings.json"

IGNORE = shutil.ignore_patterns(
    "research", ".git", "__pycache__", "*.pyc", ".ruff_cache", ".pytest_cache",
    "*.jpg", "*.png", ".behdad", "node_modules", ".venv", "venv",
)

HOOK_MATCHER = "Write|Edit|MultiEdit|NotebookEdit|Bash"


def _gate_command() -> str:
    gate = (SKILL_DST / "platform" / "claude" / "hooks" / "gate.py").as_posix()
    return f'python "{gate}"'


def install() -> None:
    # 1. Skill directory (whole portable core + platform + tests, minus research/binaries).
    if SKILL_DST.exists():
        shutil.rmtree(SKILL_DST)
    SKILL_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO, SKILL_DST, ignore=IGNORE)
    print(f"[skill]    {SKILL_DST}")

    # 2. Subagents (inspectors + critic), skipping the generator.
    AGENTS_DST.mkdir(parents=True, exist_ok=True)
    for md in (REPO / "platform" / "claude" / "agents").glob("behdad-*.md"):
        shutil.copy2(md, AGENTS_DST / md.name)
    print(f"[agents]   {AGENTS_DST}  ({len(list(AGENTS_DST.glob('behdad-*.md')))} behdad-* agents)")

    # 3. /behdad command, with BEHDAD_HOME made concrete for this install.
    COMMANDS_DST.mkdir(parents=True, exist_ok=True)
    cmd_txt = (REPO / "platform" / "claude" / "commands" / "behdad.md").read_text(encoding="utf-8")
    cmd_txt = cmd_txt.replace(
        "e.g. `~/.claude/skills/better-call-behdad`",
        f"here: `{SKILL_DST.as_posix()}`",
    )
    (COMMANDS_DST / "behdad.md").write_text(cmd_txt, encoding="utf-8", newline="\n")
    print(f"[command]  {COMMANDS_DST / 'behdad.md'}")

    # 4. Merge the fix-gate hook into settings.json (backup first, preserve everything).
    _merge_hook()
    print("\nInstalled. In a NEW Claude Code session:  /behdad <path-to-project>")
    print("The fix-gate hook is inert unless BEHDAD_ACTIVE=1, so it won't affect normal use.")


def _load_settings() -> dict:
    if SETTINGS.exists():
        try:
            return json.loads(SETTINGS.read_text(encoding="utf-8"))
        except Exception:
            print("WARNING: settings.json is not valid JSON; leaving hooks unmerged.", file=sys.stderr)
            return {}
    return {}


def _merge_hook() -> None:
    settings = _load_settings()
    if SETTINGS.exists():
        backup = SETTINGS.with_suffix(f".json.behdad-backup-{time.strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(SETTINGS, backup)
        print(f"[settings] backed up -> {backup.name}")

    hooks = settings.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    entry = {"matcher": HOOK_MATCHER, "hooks": [{"type": "command", "command": _gate_command()}]}
    # Replace any prior behdad gate entry; else append.
    pre = [e for e in pre if "gate.py" not in json.dumps(e)]
    pre.append(entry)
    hooks["PreToolUse"] = pre
    SETTINGS.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"[settings] PreToolUse fix-gate hook merged into {SETTINGS.name}")


def uninstall() -> None:
    if SKILL_DST.exists():
        shutil.rmtree(SKILL_DST)
        print(f"removed {SKILL_DST}")
    for md in AGENTS_DST.glob("behdad-*.md"):
        md.unlink(); print(f"removed {md.name}")
    cmd = COMMANDS_DST / "behdad.md"
    if cmd.exists():
        cmd.unlink(); print("removed command behdad.md")
    settings = _load_settings()
    pre = settings.get("hooks", {}).get("PreToolUse", [])
    kept = [e for e in pre if "gate.py" not in json.dumps(e)]
    if len(kept) != len(pre):
        settings["hooks"]["PreToolUse"] = kept
        SETTINGS.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        print("removed fix-gate hook from settings.json")
    print("uninstalled. (settings.json backups are kept.)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--uninstall", action="store_true")
    args = ap.parse_args()
    uninstall() if args.uninstall else install()
