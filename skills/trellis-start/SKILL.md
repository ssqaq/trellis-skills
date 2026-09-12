---
name: trellis-start
description: "Initializes an AI development session by reading workflow guides, developer identity, git status, active tasks, and project guidelines from .trellis/. Classifies incoming tasks and routes to brainstorm, direct edit, or task workflow. Use when beginning a new coding session, resuming work, starting a new task, or re-establishing project context."
---

# Start Session

## Background release check

In the main session, follow the task-triggered update section of the installed
global/project rules before loading task skills. Use the global
`trellis-setup/scripts/auto_update.py`: first `apply-pending --project-root <root>`
at an idle start boundary, then `check --background --project-root <root>
--invocation-id <unique-user-turn-id>`. Obtain `status --project-root <root>`
and load the returned `skills_source` so a busy project keeps its previous rules.
Reuse the same invocation id if continue/setup is called in this user turn.
In Plan mode only check/status are allowed; never apply, sync or migrate.
The complete behavior and errors are documented in the installed setup skill's
`references/automatic-updates.md`.

Initialize a Trellis-managed development session. This platform has no session-start hook, so manually load the equivalent compact context by following these steps.

---

## Step 1: Current state
Identity, git status, current task, active tasks, journal location.

```bash
python ./.trellis/scripts/get_context.py
```

If this output includes a line beginning `Trellis update available:`, copy the full line verbatim when summarizing session context. Do not shorten operational command hints.

## Step 2: Workflow overview
On an initialized project whose `AGENTS.md` or selected workflow lacks `TRELLIS-SKILLS:AUTOFINISH:START`,
use the current global `trellis-setup/scripts/upgrade_project.py` with
`--project-root <project-root> --sync-skills --register` to connect automatic
closeout before reading phase instructions. This also supports projects created
by a manual `trellis init`. Preserve project-specific instructions; report any
migration failure rather than assuming the route exists.
Skip this migration when status reports a deferred busy-project update.

Compact Phase Index, request triage rules, planning artifact contract, and the step-detail command.

```bash
python ./.trellis/scripts/get_context.py --mode phase
```

Full guide in `.trellis/workflow.md` (read on demand).

## Step 3: Guideline indexes
Discover packages + spec layers, then read each relevant index file.

```bash
python ./.trellis/scripts/get_context.py --mode packages
cat .trellis/spec/guides/index.md
cat .trellis/spec/<package>/<layer>/index.md   # for each relevant layer
```

Index files list the specific guideline docs to read when you actually start coding.

## Step 4: Decide next action
From Step 1 you know the current task and status. Check the task directory:

- **Active task status `planning` + no `prd.md`** → Phase 1.1. Load the `trellis-brainstorm` skill.
- **Active task status `planning` + `prd.md` exists** → stay in Phase 1. Lightweight tasks can be PRD-only; complex tasks need `design.md` + `implement.md`. Load the relevant Phase 1 step detail before `task.py start`.
- **Active task status `in_progress`** → load `trellis-continue` and route using completed artifacts and current evidence. Do not restart implementation if code and checks are already done. For work not yet implemented, load:
  ```bash
  python ./.trellis/scripts/get_context.py --mode phase --step 2.1 --platform codex
  ```
- **No active task** → classify first. For simple conversation / small task, ask only whether this turn should create a Trellis task. For complex work, ask whether you may create a Trellis task and enter planning. If the user says no, skip Trellis for this session.

---

## Skill routing (quick reference)

| User intent | Skill |
|---|---|
| New feature / unclear requirements | `trellis-brainstorm` |
| About to write code | `trellis-before-dev` |
| Done coding / quality check | `trellis-check` |
| Current task work complete, preparing final reply | `trellis-finish-work` automatically; wait for the full check and finish the archive/journal flow |
| Stuck / fixed same bug multiple times | `trellis-break-loop` |
| Learned something worth capturing | `trellis-update-spec` |

Full rules + anti-rationalization table in `.trellis/workflow.md`.
