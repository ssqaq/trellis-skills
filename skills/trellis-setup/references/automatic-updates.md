# Automatic skill package updates

The main Codex session controls the lifecycle; there is no permanent watcher.
Resolve the updater from the user's global installation, not a repository-root
`skills/` assumption. All commands are `python -B <absolute-auto_update.py> ...`.

1. At an idle task start, `apply-pending --project-root <root>` catches up a
   previously prepared release. An executing project defers this automatically.
2. At every real start/resume turn, `check --background --project-root <root>
   --invocation-id <id>` starts a short-lived hidden worker. Generate one id for
   this user turn and reuse it across nested skill calls. No hourly/daily cache.
3. `status --project-root <root>` returns the installed version, pending update
   and `skills_source`. Use that source for task skills. Busy projects retain
   their previous source even after another project updates global skills.
4. After the real finish gate, archive and journal, run `apply-pending
   --project-root <root> --wait-seconds 15`. It installs only verified packages
   and syncs idle registered projects. Busy/offline roots remain pending.

Checks read only the latest stable Release of ssqaq/trellis-skills, not the npm
CLI or default-branch source. Downloads require the release ZIP plus SHA256
asset, matching GitHub digest when supplied, matching VERSION and package files.
Errors retain the current installation. Failed installs restore managed files
from backups; concurrent user edits are preserved and reported for repair.

The registry, installed-version records, retained packages and backups live in
`<user-profile>/.trellis-skills/`. Custom registries keep isolated synchronization
state beside their registry. Existing tasks/specs/journals/business code are not
updated or committed by the installer. No update command grants GitHub push permission.

Progress-only questions, paused/stopped work, opt-out and delegated agents do not
run the updater. In Plan mode only check/status are allowed. No installer or
migration runs in read-only mode. An unavailable download after the bounded
finish wait is picked up automatically at a later start/finish boundary.

Say briefly when installation succeeds, fails or leaves projects pending. Do not
announce every unchanged version. Never claim an offline/busy project was synced.
The one-time 1.4 installation is required before these entry rules exist.

For developer-controlled isolated tests only, `--profile <temporary-profile>`
and `--release-fixture <responses.json>` select a local release transport.
Fixtures require a TEST-ONLY marker in that temporary profile's state directory.
Normal installations have no fixture or alternative update endpoint.
