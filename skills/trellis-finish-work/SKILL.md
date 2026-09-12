---
name: trellis-finish-work
description: "Wrap up the current session: run the full quality gate first, then verify the tree, archive completed tasks, and record session progress to the developer journal. Use when done coding and ready to end the session."
---

# Finish Work

Wrap up the current session: run a fresh full quality check, then archive the active task (and any other completed-but-unarchived tasks the user wants to clean up) and record the session journal. Code commits are NOT done here — those happen in workflow Phase 3.4 before you invoke this command.

## Mandatory first step: run the full quality check

This is a real gate, not a reminder to check whether somebody checked earlier.

1. At the very start of every `finish-work` run, dispatch or invoke `trellis-check` and wait for its complete result. On platforms with sub-agent support, dispatch the `trellis-check` agent. On platforms without it, read `skills/trellis-check/SKILL.md` and perform the same full check in the main session.
2. The check must cover the current task's complete diff and every affected package or layer. If the task will be pushed, tagged, or released on GitHub, include the Release notes and README checks too.
3. If the check finds a failure, stop immediately. Fix the failure and run `trellis-check` again before continuing. Do not archive the task, record a completed session, publish, push, or claim success while the gate is failing.
4. Only after the check passes may you continue to the state survey below, the dirty-tree check, task archive, and journal entry.

`finish-work` is the guaranteed entry point for this gate. A session merely becoming idle, completed, or closed is not a universal platform event and does not by itself guarantee that this skill ran. The workflow must route a completed task into `finish-work` (or the user must explicitly say to finish/close the task).

## Plain-language Release notes and README rule

When this task's outcome will be published to GitHub (push, tag, or GitHub Release), two user-facing documents MUST be plain enough for a non-developer to understand. Before considering the session wrapped:

1. **Release notes** (when a Release will be created) — confirm the notes (or the draft intended for them) answer, in this order:
   - **What changed in this update** — one numbered item per user-visible change, describing behavior, not implementation
   - **What it means for the user** — the practical benefit or impact
   - **Whether the user needs to act** — e.g. whether they must download and reinstall the new package
2. **README** (when this task changes user-visible behavior, installation, or usage and the project has a README) — confirm the README still matches reality: what the software does, how to install it, and how to use it, all in plain language.
3. Write for a non-technical reader: no bare commit-style prefixes (`feat:`, `fix:`, `chore:`), no file names, no function/class names, no internal jargon in Release notes or README user-facing text. Technical details belong in commit messages.
4. If either document does not meet this standard, rewrite it before wrapping up. If no Release will be created and no user-visible behavior/installation/usage changed, skip this rule.

Example of the required style (adapt the language to the project's normal user language):

```text
What changed in this update:
1. Login was upgraded: QR-code login and browser login now save accounts under the same rule, so accounts are no longer duplicated or mixed up.
2. Eight old test issues were fixed. These did not affect daily use, but developer test runs are now clean.

What it means for you:
Login is more stable, and logging in again with the same account will not create duplicate entries.

Do you need to do anything:
Yes. Download the new installer and replace the old version.
```

## Step 1: Survey current state after the quality gate passes

```bash
python ./.trellis/scripts/get_context.py --mode record
```

This prints:

- **My active tasks** — review whether any besides the current one are actually done (code merged, AC met) and should be archived this round.
- **Git status** — quick visual on what's dirty.
- **Recent commits** — you'll need their hashes in Step 4 for `--commit`.

If `--mode record` surfaces other completed tasks not tied to the current session, surface them to the user with a one-shot confirmation: "These N tasks look done — archive them too in this round? [y/N]". Default is no; the current active task is always archived in Step 3 regardless.

## Step 2: Sanity check — classify dirty paths

Run:

```bash
git status --porcelain
```

Filter out paths under `.trellis/workspace/` and `.trellis/tasks/` — those are managed by `add_session.py` and `task.py archive` auto-commits and will appear dirty as part of this skill's own work.

For each remaining dirty path, decide whether it belongs to **the current task** or to **other parallel work** (e.g., another terminal window editing the same repo). Heuristics:

- Paths referenced in the current task's `prd.md` / `implement.jsonl` / `check.jsonl` → current task
- Paths in code areas matching the task's stated scope, or that you remember editing this session → current task
- Paths in unrelated areas you have no recollection of touching this session → other parallel work

Then route:

- **Any remaining path looks like current-task work** — bail out with:
  > "Working tree has uncommitted code changes from this task: `<list>`. Return to workflow Phase 3.4 to commit them before running ``finish-work` (Trellis command)`."

  Do NOT run `git commit` here. Do NOT prompt the user to commit. The user goes back to Phase 3.4 and the AI drives the batched commit there.
- **All remaining paths look unrelated** (other parallel-window work) — report them once and continue to Step 3:
  > "FYI, dirty files outside this task's scope — leaving them for the other window: `<list>`."
- **Genuinely unsure** — ask the user once: "Are `<list>` this task's work I forgot to commit, or another window's? (commit / ignore)" — then route per their answer.

## Step 3: Archive task(s)

```bash
python ./.trellis/scripts/task.py archive <task-name>
```

At minimum: the current active task (if any). Plus any extra tasks the user confirmed in Step 1. Each archive produces a `chore(task): archive ...` commit via the script's auto-commit.

If there is no active task and the user did not confirm any cleanup archives, skip this step.

## Step 4: Record session journal

```bash
python ./.trellis/scripts/add_session.py \
  --title "Session Title" \
  --commit "hash1,hash2" \
  --summary "Brief summary"
```

Use the work-commit hashes produced in Phase 3.4 (visible in Step 1's `Recent commits` list, or via `git log --oneline`) for `--commit`. Do not include the archive commit hashes from Step 3. This produces a `chore: record journal` commit.

Final git log order: `<work commits from 3.4>` → `chore(task): archive ...` (one or more) → `chore: record journal`.
