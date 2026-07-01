# 05 — Claude Code Skill / Subagent Implementation

Implementation-level reference for authoring the **Better-call-behdad** multi-agent code-audit skill in Claude Code, plus how portable each mechanism is to OpenAI Codex, Cursor, and other agents. All Claude specifics are drawn from official Anthropic docs (`code.claude.com/docs`); Codex specifics from `developers.openai.com/codex`. Version markers (e.g. `v2.1.196`) are the doc's own `min-version` annotations — treat them as "requires at least this build."

---

## 1. Claude Code Skills

### 1.1 What a skill is

A skill is a **directory** whose entry point is a `SKILL.md` file (YAML frontmatter + Markdown body). Claude loads the skill automatically when its `description` matches the conversation, or you invoke it explicitly with `/skill-name`. Custom slash commands (`.claude/commands/*.md`) have been **merged into skills**: `.claude/commands/deploy.md` and `.claude/skills/deploy/SKILL.md` both produce `/deploy`; if both exist, the skill wins.

Claude Code skills follow the **Agent Skills open standard** (agentskills.io), which is the key portability hook — see §5.

### 1.2 Where skills live (precedence high → low)

| Location   | Path                                        | Applies to                     |
| :--------- | :------------------------------------------ | :----------------------------- |
| Enterprise | managed settings dir                        | All users in the org           |
| Personal   | `~/.claude/skills/<name>/SKILL.md`          | All your projects              |
| Project    | `.claude/skills/<name>/SKILL.md`            | This repo only (commit to git) |
| Plugin     | `<plugin>/skills/<name>/SKILL.md`           | Where plugin is enabled        |

- Enterprise > personal > project; a same-name skill at any level overrides a bundled skill. Plugin skills are namespaced `plugin-name:skill-name` and never conflict.
- **Command name comes from the directory name**, not the frontmatter `name` (except a plugin-root `SKILL.md`, where `name` sets it). `.claude/skills/deploy-staging/SKILL.md` → `/deploy-staging`.
- **Nested/monorepo discovery:** `.claude/skills/` is discovered walking up to repo root, and on-demand in subdirectories you touch (e.g. `apps/web/.claude/skills/deploy` becomes `/apps/web:deploy` when the name clashes).
- **Live change detection:** edits to `SKILL.md` under watched dirs take effect mid-session; *creating* a brand-new top-level skills dir needs a restart.

### 1.3 Directory structure

```text
my-skill/
├── SKILL.md            # required — overview + instructions
├── reference.md        # loaded only when SKILL.md points Claude to it
├── examples.md
└── scripts/
    └── helper.py       # executed, not loaded into context
```

**Progressive disclosure** is the core design principle:
1. **Frontmatter `description`** — always in context so Claude can decide to trigger. Combined `description` + `when_to_use` is capped at **1,536 chars** in the listing.
2. **SKILL.md body** — loads only when the skill is invoked. Keep under **500 lines**; once loaded it stays in context for the rest of the session (recurring token cost).
3. **Supporting files** — loaded only if the body references them and Claude reads them. Put large reference material here so it costs nothing until needed.

### 1.4 Full frontmatter reference

All fields optional; only `description` recommended.

```yaml
---
name: my-skill                     # display label; defaults to dir name
description: What it does + WHEN to use it (front-load trigger words)
when_to_use: extra trigger phrases # appended to description, counts to 1536 cap
argument-hint: "[issue-number]"    # autocomplete hint
arguments: [issue, branch]         # named positional args -> $issue, $branch
disable-model-invocation: true     # only user can invoke (/name); hides from Claude's context
user-invocable: false              # only Claude can invoke; hidden from / menu
allowed-tools: Read Grep           # pre-approved (no permission prompt) while active
disallowed-tools: AskUserQuestion  # removed from pool while active
model: sonnet                      # override model for this turn (or `inherit`)
effort: high                       # low|medium|high|xhigh|max
context: fork                      # run skill in an isolated subagent
agent: Explore                     # which subagent type when context: fork
hooks: {...}                       # lifecycle hooks scoped to this skill
paths: "src/**/*.ts"               # only auto-activate when working on matching files
shell: bash                        # bash (default) | powershell
---
```

**Invocation control matrix:**

| Frontmatter                      | User invokes | Claude invokes | Description in context |
| :------------------------------- | :----------- | :------------- | :--------------------- |
| (default)                        | Yes          | Yes            | Yes                    |
| `disable-model-invocation: true` | Yes          | No             | No                     |
| `user-invocable: false`          | No           | Yes            | Yes                    |

### 1.5 Dynamic context injection & substitutions

- **Shell injection:** `` !`git diff HEAD` `` runs *before* Claude sees the skill and inlines the output (preprocessing, not a tool call). Multi-line form uses a fenced ` ```! ` block. Only fires when `!` starts a line or follows whitespace. Disable org-wide with `"disableSkillShellExecution": true`.
- **String substitutions:** `$ARGUMENTS`, `$ARGUMENTS[N]` / `$N` (0-based positional), `$name` (named args), `${CLAUDE_SESSION_ID}`, `${CLAUDE_EFFORT}`, `${CLAUDE_SKILL_DIR}` (portable path to bundled scripts), `${CLAUDE_PROJECT_DIR}` (project root; v2.1.196+).

### 1.6 Running a skill in a subagent (`context: fork`)

Add `context: fork` + `agent: <type>` so the SKILL.md body becomes the **task prompt** for an isolated subagent (no conversation history). Only makes sense for skills with a concrete task, not pure reference guidelines. `agent` accepts `Explore`, `Plan`, `general-purpose`, or any custom `.claude/agents/` agent; defaults to `general-purpose`. Explore/Plan skip CLAUDE.md to stay small.

Example (research skill running read-only in Explore):

```yaml
---
name: deep-research
description: Research a topic thoroughly
context: fork
agent: Explore
---
Research $ARGUMENTS thoroughly:
1. Find relevant files using Glob and Grep
2. Read and analyze the code
3. Summarize findings with specific file references
```

### 1.7 Skill content lifecycle (matters for a long audit)

Invoked skill content enters as one message and **persists across turns** (not re-read). Auto-compaction re-attaches the most recent invocation of each skill, keeping the first **5,000 tokens** each, sharing a **25,000-token** combined budget (most-recent first; older skills may drop). If a large skill stops influencing behavior after compaction, **re-invoke it**. Skill *listing* budget is 1% of context by default — tune with `skillListingBudgetFraction` / `SLASH_COMMAND_TOOL_CHAR_BUDGET`; `/doctor` reports truncation.

---

## 2. Subagents (`.claude/agents/`)

### 2.1 Model

Each subagent runs in its **own isolated context window** with its own system prompt (the markdown body), tool set, and permissions. It does **not** see conversation history (exception: a *fork*). Claude writes a delegation message; the subagent works and returns **only a summary** to the main conversation. This is exactly the "audit workers report back a structured summary" pattern.

### 2.2 Where they live (precedence high → low)

| Location                | Scope             | Priority |
| :---------------------- | :---------------- | :------- |
| Managed settings        | Org-wide          | 1        |
| `--agents` CLI JSON     | Current session   | 2        |
| `.claude/agents/`       | Project (commit)  | 3        |
| `~/.claude/agents/`     | All your projects | 4        |
| Plugin `agents/`        | Where enabled     | 5        |

Scanned recursively (subfolders allowed; identity comes only from `name`, which must be unique per scope). Plugin subfolders *do* affect identity: `agents/review/security.md` → `my-plugin:review:security`. **Files added on disk require a session restart**; agents created via `/agents` take effect immediately.

### 2.3 Built-in subagents (reusable as audit workers)

| Agent           | Model            | Tools               | Purpose                                   |
| :-------------- | :--------------- | :------------------ | :---------------------------------------- |
| Explore         | Haiku            | read-only (no Write/Edit) | fast codebase search/analysis       |
| Plan            | inherits         | read-only           | research during plan mode                 |
| general-purpose | inherits         | all tools           | multi-step explore + modify               |

Explore/Plan **skip CLAUDE.md and git status** to stay cheap; all others load them.

### 2.4 Full frontmatter reference (only `name`, `description` required)

```yaml
---
name: security-auditor          # lowercase-hyphen; hooks see this as agent_type
description: When to delegate here. Add "use proactively" to encourage delegation.
tools: Read, Grep, Glob, Bash   # allowlist; omit = inherit all
disallowedTools: Write, Edit    # denylist (applied before `tools`)
model: haiku                    # sonnet|opus|haiku|fable|<full-id>|inherit (default inherit)
effort: high                    # low|medium|high|xhigh|max — per-agent reasoning effort
permissionMode: default         # default|acceptEdits|auto|dontAsk|bypassPermissions|plan
maxTurns: 20                    # cap agentic turns
skills: [api-conventions]       # PRELOAD full skill content at startup
mcpServers: [...]               # scope MCP servers to this agent (inline or by name)
hooks: {...}                    # lifecycle hooks scoped to this agent
memory: project                 # user|project|local — persistent cross-session memory dir
background: true                # always run as background task
isolation: worktree             # run in a temp git worktree (isolated copy)
color: blue                     # UI color
initialPrompt: "..."            # auto first turn when run as main via --agent
---
System prompt (Markdown body) goes here.
```

- **Tool resolution:** `disallowedTools` first, then `tools` allowlist against the remainder. MCP patterns supported: `mcp__<server>`, `mcp__<server>__*`, `mcp__*`. `AskUserQuestion`, `EnterPlanMode`, `ScheduleWakeup`, `WaitForMcpServers` are **never** available to subagents.
- **Per-agent model + effort** are both first-class frontmatter fields — you can route cheap breadth work to Haiku/low and deep reasoning to Opus/high.
- **`skills` preloads full content** at startup (vs. just the description in a normal session) — good for giving an audit worker fixed rubric/standards.
- **Plugin subagents ignore** `hooks`, `mcpServers`, `permissionMode` for security.

### 2.5 Model resolution order

1. `CLAUDE_CODE_SUBAGENT_MODEL` env var (forces one model on every subagent — cost ceiling / compliance)
2. per-invocation `model` param Claude passes
3. the subagent's `model` frontmatter
4. main conversation's model

(As of v2.1.196, env var = `inherit` behaves like unset.) All values are checked against the org's `availableModels` allowlist.

### 2.6 Spawning & coordinating (the multi-agent core)

- **Automatic delegation** off the `description`; **explicit** via natural language ("Use the X subagent…"), `@"X (agent)"` @-mention (guarantees it), or `claude --agent X` / `agent` setting (whole session runs as that agent).
- **Restrict which agents an orchestrator can spawn** (allowlist) via the `tools` field: `tools: Agent(worker, researcher), Read, Bash`. `Agent` (no parens) = spawn any; omit `Agent` entirely = can't spawn any. (Note: the `Agent(type)` allowlist only applies to a main-thread `--agent`; inside a plain subagent, listing `Agent` lets it spawn but the parenthesized list is ignored.)
- **Parallel research:** "Research the auth, database, and API modules in parallel using separate subagents" — each isolated, Claude synthesizes. Warning: many detailed returns consume main context.
- **Chaining:** "Use code-reviewer to find issues, then optimizer to fix them" — results pass main→next.
- **Nested subagents** (v2.1.172+): a subagent can spawn its own subagents; **depth limit is 5, fixed/non-configurable**; only the top-level summary returns to you.
- **Background vs foreground:** `background: true` or Ctrl+B; background permission prompts surface in main session (v2.1.186+).

### 2.7 How structured results pass back

- A non-fork subagent returns only its **final summary message** to the main conversation — verbose logs/reads stay in its own window. To get structured output, **specify the shape in the delegation prompt / the agent's system prompt** (e.g. "return findings as: Critical / Warning / Suggestion, each with file:line and a fix"). There is no enforced JSON schema on the return — you engineer it via the prompt.
- **Resuming:** on completion Claude gets an `agent_id`; it resumes via the `SendMessage` tool (`to` = agent id/name), retaining full history. Explore/Plan are one-shot (no id, not resumable) — use `general-purpose` or a custom agent when you need continuation. Transcripts persist at `~/.claude/projects/{project}/{sessionId}/subagents/agent-{id}.jsonl`.
- For sustained parallelism beyond one session, see **agent teams** (`/en/agent-teams`), which give each worker its own context and structured team-protocol messages.

### 2.8 Forks vs named subagents

A **fork** inherits the *entire* conversation (same system prompt, tools, model, history) — cheaper (shares prompt cache) and needs no re-briefing, but drops input isolation. Named subagent = fresh context from its definition file. Enable with `CLAUDE_CODE_FORK_SUBAGENT=1` or `/fork <directive>`. A fork can't spawn another fork.

### 2.9 Constraining a worker with hooks

`PreToolUse` hooks in agent frontmatter give finer control than `tools` (e.g. allow `Bash` but only read-only SQL — script exits 2 to block writes). See §3.

---

## 3. Slash commands & hooks

### 3.1 Slash commands

Now a **subset of skills**. Legacy `.claude/commands/<name>.md` still works and supports the same frontmatter, but skills are recommended (support bundled files, auto-invocation, `context: fork`). For a manual-only command, author it as a skill with `disable-model-invocation: true`. `$ARGUMENTS` / `$N` substitution as in §1.5.

### 3.2 Hooks — deterministic lifecycle automation

Hooks are user-defined shell commands / HTTP endpoints / LLM prompts / MCP tools / sub-agents that fire at lifecycle points. Configured in `settings.json` (`~/.claude/`, `.claude/`, or `.claude/settings.local.json`), **or scoped inside a skill/agent's `hooks` frontmatter**.

**Events** (Can-block in parens): `SessionStart`, `Setup`, `UserPromptSubmit`(Y), `UserPromptExpansion`(Y), `PreToolUse`(Y), `PostToolUse`(Y), `PostToolUseFailure`, `PermissionRequest`(Y), `PermissionDenied`, `PostToolBatch`(Y), `Stop`(Y), `SubagentStart`, `SubagentStop`(Y), `FileChanged`, `CwdChanged`, `SessionEnd`.

**Config schema:**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "if": "Bash(rm *)",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/block-rm.sh",
            "args": [],
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

- **`matcher`:** tool name (`Bash`, `Edit|Write`, regex, `mcp__server__.*`); for `SessionStart` it's `startup|resume|clear|compact`; omit to match all.
- **Hook types:** `command` (stdin JSON in, exit-code/stdout out), `http` (same JSON as POST body), `prompt` (LLM yes/no), `agent` (spawns a reviewer agent — experimental), `mcp_tool`.
- **stdin JSON** includes `session_id`, `cwd`, `permission_mode`, `hook_event_name`, `tool_name`, `tool_input`, `agent_type`, etc.
- **Exit codes:** `0` = success (stdout parsed for JSON output; reaches Claude only for `UserPromptSubmit`/`UserPromptExpansion`/`SessionStart`); **`2` = blocking error** (blocks the tool/prompt/stop, stderr → Claude); other = non-blocking.
- **JSON output** can set `permissionDecision: allow|deny|ask|defer`, `updatedInput`, `additionalContext`, `decision: block` + `reason`.
- **Subagent hooks:** in frontmatter, a `Stop` hook auto-converts to `SubagentStop`. Project-level `SubagentStart`/`SubagentStop` hooks (matcher = agent name) run in the main session — useful for setup/cleanup or logging worker results in the audit.

**Use cases for the audit skill:** enforce read-only workers (`PreToolUse` block writes), lint/format after edits (`PostToolUse` on `Edit|Write`), inject repo context at `SessionStart`, capture each worker's completion (`SubagentStop`), block risky commands deterministically rather than trusting the model.

---

## 4. Packaging: plugins

To ship the whole audit system (skill + worker subagents + hooks + MCP) as one unit, use a **plugin**: a `skills/` dir, an `agents/` dir, `hooks/`, `.mcp.json`. Distribute via a marketplace (`/plugin install skill-creator@claude-plugins-official`). Note the security carve-out: plugin subagents ignore `hooks`/`mcpServers`/`permissionMode`. Adding `.claude-plugin/plugin.json` to a skill folder promotes it to a plugin (`<name>@skills-dir`) so it can bundle agents/hooks/MCP.

---

## 5. Cross-agent portability

### 5.1 The shared standard: Agent Skills + AGENTS.md

Two independent open standards make the design portable:

- **Agent Skills** (agentskills.io) — the `SKILL.md` directory+frontmatter format. **Both Claude Code and OpenAI Codex implement it.** The `name` + `description` + Markdown-body core is portable; Claude-only extensions are `context: fork`, `disable-model-invocation`, dynamic `` !`cmd` `` injection, `${CLAUDE_*}` substitutions, and per-skill `hooks`.
- **AGENTS.md** (agents.md) — plain-Markdown project instructions, now stewarded by the Agentic AI Foundation (Linux Foundation). Read by Codex, Cursor, and many others. This is the lowest-common-denominator layer.

### 5.2 OpenAI Codex

**Skills** — directory-based, `SKILL.md` with required `name` + `description`, optional `scripts/`, `references/`, `assets/`, plus optional `agents/openai.yaml` metadata (display name, icon, `policy.allow_implicit_invocation`, tool dependencies).
- Discovery scopes: `.agents/skills` (CWD → parent → repo root), `$HOME/.agents/skills` (user), `/etc/codex/skills` (admin), built-in. **Note the path differs from Claude's `.claude/skills/`.**
- Invocation: explicit `/skills` or `$skill-name`; implicit matching capped at 2% context / 8,000 chars (vs Claude's 1% / 1,536-char description cap).

**Subagents** — defined as **TOML** files in `~/.codex/agents/` (personal) or `.codex/agents/` (project). Required: `name`, `description`, `developer_instructions`. Optional: `model`, `model_reasoning_effort` (`"medium"`/`"high"`), `sandbox_mode` (`"read-only"`/`"workspace-write"`), `mcp_servers`, `skills.config`, `nickname_candidates`. Spawned via natural language ("spawn one agent per point, wait for all, summarize") or a `spawn_agents_on_csv` batch tool; workers call `report_agent_job_result` with JSON matching an `output_schema` — Codex **does** offer a structured-result mechanism that Claude leaves to prompt engineering.

**AGENTS.md config** — `~/.codex/config.toml` knobs: `project_doc_max_bytes` (default 32 KiB), `project_doc_fallback_filenames`. Precedence: `~/.codex/AGENTS.override.md` → `~/.codex/AGENTS.md` → project root-down (each dir: `AGENTS.override.md` → `AGENTS.md` → fallbacks), concatenated root→leaf so closer files override.

**Mapping Claude → Codex:**

| Claude Code                 | Codex equivalent                          |
| :-------------------------- | :---------------------------------------- |
| `.claude/skills/x/SKILL.md` | `.agents/skills/x/SKILL.md`               |
| `.claude/agents/x.md` (YAML)| `.codex/agents/x.toml`                    |
| `model` / `effort`          | `model` / `model_reasoning_effort`        |
| `tools`/`permissionMode`    | `sandbox_mode` (coarser: read-only/write) |
| CLAUDE.md                   | AGENTS.md                                  |
| hooks (settings.json)       | *no direct equivalent* (Claude-specific)  |

### 5.3 Cursor

- **Rules** live in `.cursor/rules/` as `.mdc` files (YAML frontmatter: `description`, `globs`, `alwaysApply`) — as of Cursor 2.2 new rules are **folders** with a `RULE.md`. Rule types: Always / Auto-Attached (by `globs`) / Agent-Requested (by `description`) / Manual. This maps conceptually to Claude's `paths` + `description` auto-activation, but Cursor rules are **instruction context only** — no bundled scripts, no tool-permission control, no subagent spawning.
- Cursor also reads **AGENTS.md**, so shared project context is portable there.

### 5.4 Portability guidance for Better-call-behdad

1. **Author the canonical skill as standards-compliant Agent Skills** (`SKILL.md`: `name`, `description`, Markdown body, `scripts/`, `references/`). This runs on both Claude Code and Codex.
2. **Keep Claude-only power features isolated** (dynamic `` !`cmd` `` injection, `context: fork`, per-skill hooks, `${CLAUDE_*}` vars) so a Codex/Cursor build can degrade gracefully.
3. **Express orchestration twice:** Claude via `.claude/agents/*.md` (rich: per-agent model+effort+tools+hooks+memory) and Codex via `.codex/agents/*.toml` (model + reasoning_effort + sandbox_mode). Cursor can't spawn workers — treat it as single-agent + rules.
4. **Put durable, tool-agnostic project context in AGENTS.md** (mirrored to CLAUDE.md for Claude) so every agent shares the same ground truth.
5. **Structured results:** on Codex lean on `output_schema` / `report_agent_job_result`; on Claude, specify the exact output shape in each worker's system prompt and optionally enforce/collect via a `SubagentStop` hook.
6. **Enforcement (read-only workers, blocked commands) is Claude-only via hooks**; on Codex approximate with `sandbox_mode: read-only`; on Cursor there is no enforcement layer.

---

## Sources

Official Anthropic (Claude Code):
- [Extend Claude with skills](https://code.claude.com/docs/en/skills)
- [Create custom subagents](https://code.claude.com/docs/en/sub-agents)
- [Hooks reference](https://code.claude.com/docs/en/hooks)
- [Agent Skills overview (platform docs)](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Slash Commands in the SDK](https://platform.claude.com/docs/en/agent-sdk/slash-commands)

Official OpenAI (Codex):
- [Agent Skills – Codex](https://developers.openai.com/codex/skills)
- [Subagents – Codex](https://developers.openai.com/codex/subagents)
- [Custom instructions with AGENTS.md – Codex](https://developers.openai.com/codex/guides/agents-md)
- [Advanced Configuration – Codex](https://developers.openai.com/codex/config-advanced)
- [openai/codex docs/agents_md.md](https://github.com/openai/codex/blob/main/docs/agents_md.md)

Open standards / other agents:
- [Agent Skills standard (agentskills.io)](https://agentskills.io)
- [AGENTS.md standard](https://agents.md/)
- [Cursor rules reference (community)](https://github.com/sanjeed5/awesome-cursor-rules-mdc/blob/main/cursor-rules-reference.md)
- [anthropics/claude-code skill-development SKILL.md](https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/skill-development/SKILL.md)
