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

## Step 4: Report readiness

Report in plain language, in this order:

1. Whether this project has its `.trellis/` cabinet (initialized / just created / failed)
2. The Trellis CLI status and version
3. What the user can do next: start working normally — Trellis skills (trellis-start, trellis-check, etc.) trigger automatically during task work; no special command is needed

Do not create any Trellis task in this step. Task creation is a separate decision the user makes after setup.
