# Installing Better-call-behdad

Two supported hosts: **Claude Code** and **OpenAI Codex**. The audit logic is identical; only the
thin orchestration bindings differ. Optional but recommended: install the scanners for full recall
(`pip install ruff bandit semgrep`, plus `gitleaks`, `osv-scanner`, `trivy` from their installers).
Behdad works without them — it just reports reduced recall.

## Claude Code

```bash
git clone https://github.com/mathofdynamic/better-call-behdad.git
cd better-call-behdad
python platform/claude/install.py
```

This installs to your user config (`~/.claude/`):
- the skill → `~/.claude/skills/better-call-behdad/`
- 8 subagents → `~/.claude/agents/behdad-*.md`
- the command → `~/.claude/commands/behdad.md`
- the fix-gate hook → merged into `~/.claude/settings.json` (backed up first; inert unless a run is active)

Then, in a **new** Claude Code session:
```
/behdad path/to/your/project
```
or just ask: *"audit this project with behdad."*

Update by re-running `python platform/claude/install.py`. Remove with `--uninstall`.

## OpenAI Codex

```bash
git clone https://github.com/mathofdynamic/better-call-behdad.git
```
Then, from your project (or globally):
- Copy the agent bindings into Codex's agents dir:
  `cp better-call-behdad/platform/codex/agents/behdad-*.toml <your>/.codex/agents/`
- Point Codex at the skill root (`better-call-behdad/`) so the agents can read
  `$BEHDAD_HOME/agents/**`, `$BEHDAD_HOME/scripts/**`, and `$BEHDAD_HOME/config/**`.
- Codex reads the repo's `AGENTS.md` for project context automatically.

Invoke the **manager** flow (see `agents/manager.md` / `SKILL.md`) against a target project. The
manager runs the deterministic scanners, fans out the inspector agents, gates findings through the
critic, and presents the report before any change.

## Verify your install

```bash
python tests/eval/run_eval.py     # deterministic scorecard; expect all checks green
python scripts/tool_registry.py   # shows which scanners are installed vs missing
```

## Safety model (read once)

Behdad never edits your code before you approve. On Claude Code a `PreToolUse` hook hard-blocks
writes until you confirm the action report (default-deny over Bash **and** PowerShell); fixes are
applied on a snapshot and **auto-rolled-back** if verification fails. On Codex there is **no
Behdad-level execution gate** — inspection runs in the read-only sandbox and the fix phase relies
on Codex's own approval prompts, so review the action report before granting any write approval. Treat any repo you audit as the untrusted input it is — Behdad is hardened
against prompt injection from the code under review, but you remain in the loop for every change.
