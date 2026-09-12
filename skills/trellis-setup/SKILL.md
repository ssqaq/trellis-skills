---
name: trellis-setup
description: "Set up Trellis for the current project: check global skills and the Trellis CLI, run `trellis init` when the project has no `.trellis/` cabinet yet, and report readiness. Use when the user says to initialize/setup Trellis in this project or when a Trellis task cannot start because the project is not initialized."
---

# Trellis Setup

Initialize Trellis for the current project, or verify it is already working. Do this before any Trellis task is created in this project.

## Step 1: Check whether this project already has a cabinet

Check for `.trellis/` in the current working directory:

```bash
Test-Path .trellis   # PowerShell
ls -d .trellis       # bash/zsh
```

- If `.trellis/` exists → this project is already initialized. Do NOT run `trellis init` again. Report the Trellis version (`.trellis/.version` if present) and go to Step 4.
- If it does not exist → continue to Step 2.

## Step 2: Check the Trellis CLI

```bash
trellis --version
```

- If the command works → continue to Step 3.
- If the command is not found → stop and tell the user exactly one fix:

  ```bash
  npm install -g @mindfoldhq/trellis
  ```

  Then ask them to run setup again after installing. Do not attempt the npm install yourself unless the user explicitly asks.

## Step 3: Initialize the project

Run from the project root:

```bash
trellis init
```

Then verify `.trellis/` now exists. If init fails, report the exact error message and the command to retry; do not guess at fixes.

## Step 4: Connect automatic closeout and register this project

After initialization (including an already initialized project), run the bundled
`scripts/upgrade_project.py` using its absolute installed location:

```text
python <this-skill-directory>/scripts/upgrade_project.py --project-root <project-root> --sync-skills --register
```

Prefer this skill's current global installation as the source when `trellis init`
has just generated older project-local skills. The helper refreshes existing
project skill copies from its sibling Trellis skills, adds the closeout route to
`AGENTS.md`, the main workflow and saved workflow variants, and registers the
project for future installer upgrades. Originals are backed up outside the
project under `~/.trellis-skills/backups/`. It does not change tasks, specs,
journals or business code. If migration fails, report the actual failure; do not
claim automatic closeout is ready. Never rerun `trellis init` to repair this route.

## Step 5: Report readiness

Report in plain language, in this order:

1. Whether this project has its `.trellis/` cabinet (initialized / just created / failed)
2. The Trellis CLI status and version
3. Whether automatic closeout is connected and the project is registered for upgrades
4. What the user can do next: start working normally. On completion of a normal Trellis coding task, the main session continues into finish-work and its quality check without a separate user reminder. This does not run when the app is closed or the user pauses the task.

Do not create any Trellis task in this step. Task creation is a separate decision the user makes after setup.
