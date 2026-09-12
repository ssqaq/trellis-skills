"""Independent behavioral review; every install uses a disposable profile.

Run with: python -B -m unittest discover -s tests -p test_auto_update_review.py -v
No test contacts GitHub or reads an existing user profile. Modules are snapshotted
once per run so concurrent implementation edits do not change an executing test.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import zipfile


SOURCE = Path(__file__).resolve().parents[1] / "skills/trellis-setup/scripts"
MODULE_BYTES = {name: (SOURCE / name).read_bytes() for name in (
    "upgrade_project.py", "local_install.py", "auto_update.py")}
MODULE_SNAPSHOT = tempfile.TemporaryDirectory(prefix="trellis-review-modules-")
for _name, _raw in MODULE_BYTES.items():
    (Path(MODULE_SNAPSHOT.name) / _name).write_bytes(_raw)
sys.path.insert(0, MODULE_SNAPSHOT.name)
import local_install as local
import auto_update as updater
sys.path.pop(0)


class AutoUpdateReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="trellis-auto-review-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.assertTrue(self.base.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.profile = self.base / "profile"
        self.profile.mkdir()
        self.project = self.base / "project"
        self.put(self.project / ".trellis/workflow.md", b"# Custom workflow\nKeep team rules.\n")
        self.put(self.project / "AGENTS.md", b"# User project rules\n")
        self.put(self.project / ".agents/skills/trellis-start/SKILL.md", b"pre-existing project skill")
        self.env = dict(os.environ, USERPROFILE=str(self.profile), PYTHONDONTWRITEBYTECODE="1")

    @staticmethod
    def put(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def package(self, version, *, obsolete=False):
        package = self.base / ("source-" + version)
        self.put(package / "VERSION", version.encode())
        for name in ("install.ps1", "sync-local-skills.ps1", "uninstall.ps1"):
            self.put(package / name, b"# fixture wrapper\n")
        for name in ("trellis-start", "trellis-continue", "trellis-finish-work", "trellis-check", "trellis-setup"):
            self.put(package / "skills" / name / "SKILL.md", (name + " " + version).encode())
        for name, raw in MODULE_BYTES.items():
            self.put(package / "skills/trellis-setup/scripts" / name, raw)
        if obsolete:
            self.put(package / "skills/trellis-start/obsolete-rule.md", b"old managed rule")
        return package

    def install(self, source):
        return local.install(source, self.profile, project_roots=[self.project])

    def state(self):
        return local.read_json(self.profile / ".trellis-skills/installed.json", {})

    def task(self, status):
        self.put(self.project / ".trellis/tasks/active/task.json", json.dumps({"status": status}).encode())

    def bootstrap(self, **overrides):
        # Full record shape from trellis init's getBootstrapTaskJson and
        # trellis-core emptyTaskRecord, inspected from the installed CLI.
        record = {
            "id": "00-bootstrap-guidelines", "name": "00-bootstrap-guidelines",
            "title": "Bootstrap Guidelines", "description": "Fill in project development guidelines for AI agents",
            "status": "in_progress", "dev_type": "docs", "scope": None, "package": None,
            "priority": "P1", "creator": "review", "assignee": "review", "createdAt": "2026-09-12",
            "completedAt": None, "branch": None, "base_branch": None, "worktree_path": None,
            "commit": None, "pr_url": None, "subtasks": [], "children": [], "parent": None,
            "relatedFiles": [".trellis/spec/backend/", ".trellis/spec/frontend/"],
            "notes": "First-time setup task created by trellis init (fullstack project)", "meta": {},
        }
        record.update(overrides)
        path = self.project / ".trellis/tasks/00-bootstrap-guidelines/task.json"
        self.put(path, json.dumps(record, indent=2).encode())
        self.put(path.with_name("prd.md"), b"# Bootstrap Task: Fill Project Development Guidelines\n\n- [ ] Fill backend guidelines\n- [ ] Fill frontend guidelines\n- [ ] Add code examples\n")
        return path

    def served_release(self, source, *, corrupt_checksum=False):
        version = (source / "VERSION").read_text()
        filename = f"trellis-skills-{version}.zip"
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    archive.writestr(f"trellis-skills-{version}/" + path.relative_to(source).as_posix(), path.read_bytes())
        payload = stream.getvalue()
        digest = hashlib.sha256(payload).hexdigest()
        expected = "0" * 64 if corrupt_checksum else digest
        base_url = f"https://github.com/ssqaq/trellis-skills/releases/download/v{version}/"
        release = {"tag_name": "v" + version, "draft": False, "prerelease": False, "assets": [
            {"name": filename, "browser_download_url": base_url + filename},
            {"name": filename + ".sha256", "browser_download_url": base_url + filename + ".sha256"},
        ]}
        responses = {
            updater.API: json.dumps(release).encode(),
            base_url + filename: payload,
            base_url + filename + ".sha256": f"{expected}  {filename}\n".encode(),
        }
        def reader(url, limit, **kwargs):
            raw = responses[url]
            self.assertLessEqual(len(raw), limit)
            return raw
        return reader

    def test_write_failure_rolls_back_files_and_version(self):
        old, new = self.package("1.4.0"), self.package("1.4.1")
        self.install(old)
        installed = (self.profile / ".trellis-skills/installed.json").read_bytes()
        target = self.profile / ".agents/skills/trellis-finish-work/SKILL.md"
        original_write = local.migration.atomic_write
        def failing_write(path, raw):
            if path == target and raw.endswith(b"1.4.1"):
                raise OSError("fixture disk write failure")
            return original_write(path, raw)
        with mock.patch.object(local.migration, "atomic_write", side_effect=failing_write):
            with self.assertRaises(OSError):
                self.install(new)
        self.assertEqual((self.profile / ".trellis-skills/installed.json").read_bytes(), installed)
        self.assertEqual(target.read_bytes(), (old / "skills/trellis-finish-work/SKILL.md").read_bytes())
        self.assertEqual((self.project / ".agents/skills/trellis-start/SKILL.md").read_bytes(), (old / "skills/trellis-start/SKILL.md").read_bytes())

    def test_crashed_transaction_recovers_before_next_install(self):
        old, new = self.package("1.4.0"), self.package("1.4.1")
        self.install(old)
        target = self.profile / ".agents/skills/trellis-start/SKILL.md"
        program = """import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import local_install as local
original = local.migration.atomic_write
def crash_after_write(path, raw):
    original(path, raw)
    if str(path) == sys.argv[5] and raw.endswith(b'1.4.1'):
        os._exit(71)
local.migration.atomic_write = crash_after_write
local.install(Path(sys.argv[2]), Path(sys.argv[3]), project_roots=[Path(sys.argv[4])])
"""
        result = subprocess.run([sys.executable, "-B", "-c", program, MODULE_SNAPSHOT.name, str(new), str(self.profile), str(self.project), str(target)], cwd=self.base, env=self.env, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 71, result.stderr)
        self.assertEqual(self.state()["version"], "1.4.0")
        self.install(old)
        self.assertEqual(target.read_bytes(), (old / "skills/trellis-start/SKILL.md").read_bytes())
        self.assertTrue(local.read_json(self.profile / ".trellis-skills/transaction.json")["committed"])

    def test_second_process_cannot_install_under_owned_lock(self):
        source = self.package("1.4.0")
        program = """import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import local_install as local
try:
    local.install(Path(sys.argv[2]), Path(sys.argv[3]))
except BlockingIOError:
    raise SystemExit(72)
"""
        with local.lock(self.profile / ".trellis-skills/install.lock"):
            result = subprocess.run([sys.executable, "-B", "-c", program, MODULE_SNAPSHOT.name, str(source), str(self.profile)], cwd=self.base, env=self.env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 72, result.stderr)
        self.assertFalse((self.profile / ".trellis-skills/installed.json").exists())

    def test_busy_project_keeps_old_source_and_old_version(self):
        self.install(self.package("1.4.0"))
        self.task("in_progress")
        self.install(self.package("1.4.1"))
        item = self.state()["projects"][str(self.project)]
        self.assertEqual((item["version"], item["pending_version"]), ("1.4.0", "1.4.1"))
        source = Path(local.project_source(self.profile, self.project))
        self.assertEqual((source / "trellis-start/SKILL.md").read_bytes(), b"trellis-start 1.4.0")

    def test_first_install_busy_local_only_project_has_usable_old_source(self):
        self.task("in_progress")
        self.install(self.package("1.4.0"))
        selected = Path(local.project_source(self.profile, self.project)) / "trellis-start/SKILL.md"
        self.assertTrue(selected.is_file(), "Busy local-only project was assigned a nonexistent pinned source")
        self.assertEqual(selected.read_bytes(), b"pre-existing project skill")

    @unittest.skipUnless(os.name == "nt", "Windows path identity regression")
    def test_global_status_keeps_busy_pin_with_different_path_casing(self):
        target = self.project / ".agents/skills/trellis-start/SKILL.md"
        target.unlink()
        for directory in (target.parent, target.parent.parent, target.parent.parent.parent):
            directory.rmdir()
        self.install(self.package("1.4.0"))
        self.task("in_progress")
        self.install(self.package("1.4.1"))
        alternate = Path(str(self.project).swapcase())
        self.assertTrue(alternate.samefile(self.project))
        helper = self.profile / ".agents/skills/trellis-setup/scripts/auto_update.py"
        result = subprocess.run([sys.executable, "-B", str(helper), "status", "--profile", str(self.profile),
                                 "--project-root", str(alternate)], cwd=self.base, env=self.env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        selected = Path(json.loads(result.stdout)["skills_source"])
        self.assertEqual((selected / "trellis-start/SKILL.md").read_bytes(), b"trellis-start 1.4.0",
                         "Equivalent Windows path bypassed the busy project's old pin")

    def test_legacy_setup_helper_cannot_overwrite_pending_busy_project(self):
        self.install(self.package("1.4.0"))
        self.task("in_progress")
        self.install(self.package("1.4.1"))
        skill = self.project / ".agents/skills/trellis-start/SKILL.md"
        before = skill.read_bytes()
        before_state = self.state()["projects"][str(self.project)]
        helper = self.profile / ".agents/skills/trellis-setup/scripts/upgrade_project.py"
        result = subprocess.run([sys.executable, "-B", str(helper), "--project-root", str(self.project),
                                 "--sync-skills", "--register"], cwd=self.base, env=self.env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(skill.read_bytes(), before,
                         f"Setup helper overwrote a busy project while state stayed {before_state}: {result.stdout}")
        self.assertEqual(self.state()["projects"][str(self.project)], before_state)

    def test_unselected_default_bootstrap_allows_install_and_normal_task_closeout(self):
        record = self.bootstrap()
        originals = {path: path.read_bytes() for path in record.parent.iterdir()}
        first = self.install(self.package("1.4.0"))
        self.assertIn(str(self.project), first["projects_updated"])
        self.assertFalse(first["pending_projects"])
        self.task("in_progress")
        self.assertEqual(updater.check_now(self.profile, reader=self.served_release(self.package("1.4.1")))["status"], "ready")
        self.assertEqual(updater.apply_pending(self.profile, self.project)["status"], "deferred")
        self.task("completed")
        result = updater.apply_pending(self.profile, self.project)
        self.assertEqual(result["status"], "updated", result)
        self.assertEqual(self.state()["projects"][str(self.project)]["version"], "1.4.1")
        self.assertNotIn("pending_version", self.state()["projects"][str(self.project)])
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_selected_bootstrap_stays_busy_for_legacy_and_session_pointers(self):
        self.install(self.package("1.4.0"))
        record = self.bootstrap()
        before_record = record.read_bytes()
        skill = self.project / ".agents/skills/trellis-start/SKILL.md"
        before_skill = skill.read_bytes()
        new = self.package("1.4.1")
        reference = ".trellis/tasks/00-bootstrap-guidelines"
        cases = (
            (self.project / ".trellis/.current-task", reference.encode()),
            (self.project / ".trellis/.runtime/sessions/codex_review.json", json.dumps({
                "platform": "codex", "last_seen_at": "2026-09-12T00:00:00Z", "session_id": "review",
                "current_task": reference, "current_run": None}).encode()),
        )
        for pointer, raw in cases:
            with self.subTest(pointer=pointer.name):
                self.put(pointer, raw)
                try:
                    self.assertTrue(local.busy(self.project))
                    result = self.install(new)
                    self.assertIn({"project": str(self.project), "reason": "busy"}, result["pending_projects"])
                    self.assertEqual(skill.read_bytes(), before_skill)
                    self.assertEqual(record.read_bytes(), before_record)
                finally:
                    pointer.unlink()

    def test_bootstrap_with_real_work_evidence_remains_busy(self):
        self.install(self.package("1.4.0"))
        new = self.package("1.4.1")
        for field, value in (("branch", "work/bootstrap"), ("worktree_path", str(self.base / "worktree")),
                             ("commit", "a" * 40), ("pr_url", "https://example.invalid/review"),
                             ("meta", {"started_at": "2026-09-12T00:00:00Z"})):
            with self.subTest(field=field):
                record = self.bootstrap(**{field: value})
                before = record.read_bytes()
                self.assertTrue(local.busy(self.project))
                self.assertIn({"project": str(self.project), "reason": "busy"}, self.install(new)["pending_projects"])
                self.assertEqual(record.read_bytes(), before)
                self.assertEqual((self.project / ".agents/skills/trellis-start/SKILL.md").read_bytes(), b"trellis-start 1.4.0")

    def test_explicitly_paused_bootstrap_is_not_an_untouched_template(self):
        self.install(self.package("1.4.0"))
        record = self.bootstrap(status="paused")
        before = record.read_bytes()
        result = self.install(self.package("1.4.1"))
        self.assertIn({"project": str(self.project), "reason": "busy"}, result["pending_projects"],
                      "Explicitly paused bootstrap was treated as an untouched in_progress template")
        self.assertEqual(record.read_bytes(), before)

    def test_offline_project_retains_previous_version_and_resumes(self):
        self.install(self.package("1.4.0"))
        parked = self.base / "offline-project"
        self.assertTrue(parked.is_relative_to(self.base))
        self.project.rename(parked)
        new = self.package("1.4.1")
        self.install(new)
        item = self.state()["projects"][str(self.project)]
        self.assertEqual((item["version"], item["pending_version"], item["reason"]), ("1.4.0", "1.4.1", "offline"))
        self.assertIn(str(self.project), local.read_json(self.profile / ".trellis-skills/projects.json")["projects"])
        parked.rename(self.project)
        self.install(new)
        self.assertEqual(self.state()["projects"][str(self.project)]["version"], "1.4.1")
        self.assertNotIn("pending_version", self.state()["projects"][str(self.project)])

    def test_busy_project_skipping_version_removes_previously_managed_files(self):
        self.install(self.package("1.4.0", obsolete=True))
        stale = self.project / ".agents/skills/trellis-start/obsolete-rule.md"
        self.assertTrue(stale.exists())
        self.task("in_progress")
        self.install(self.package("1.4.1"))
        self.assertTrue(stale.exists())
        self.task("completed")
        self.install(self.package("1.4.2"))
        self.assertEqual(self.state()["projects"][str(self.project)]["version"], "1.4.2")
        self.assertFalse(stale.exists(), "Project marked current retains a file removed while it was busy")

    def test_manifest_relative_escape_cannot_delete_unmanaged_user_file(self):
        self.install(self.package("1.4.0"))
        sentinel = self.base / "unmanaged-user-file.txt"
        self.put(sentinel, b"keep")
        state = self.state()
        state["managed_files"].append("../../../unmanaged-user-file.txt")
        local.write_json(self.profile / ".trellis-skills/installed.json", state)
        # Use one global target so a duplicate project write cannot mask an
        # escaping deletion by triggering the transaction's conflict rollback.
        local.write_json(self.profile / ".trellis-skills/projects.json", {"projects": []})
        try:
            local.install(self.package("1.4.1"), self.profile)
        except (ValueError, RuntimeError):
            pass
        self.assertTrue(sentinel.is_file(), "Managed manifest path escaped the skill root and deleted a user file")
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_network_error_does_not_change_installed_version(self):
        self.install(self.package("1.4.0"))
        before = (self.profile / ".trellis-skills/installed.json").read_bytes()
        def offline(*args, **kwargs):
            raise OSError("fixture offline")
        result = updater.check_now(self.profile, reader=offline)
        self.assertEqual(result["status"], "failed")
        self.assertEqual((self.profile / ".trellis-skills/installed.json").read_bytes(), before)

    def test_bad_sha256_does_not_create_ready_update(self):
        self.install(self.package("1.4.0"))
        result = updater.check_now(self.profile, reader=self.served_release(self.package("1.4.1"), corrupt_checksum=True))
        self.assertEqual(result["status"], "failed")
        self.assertIn("SHA256", result["message"])
        self.assertFalse(local.read_json(self.profile / ".trellis-skills/update.json").get("ready"))
        self.assertEqual(self.state()["version"], "1.4.0")

    def test_verified_release_is_cached_then_installed_only_when_idle(self):
        self.install(self.package("1.4.0"))
        result = updater.check_now(self.profile, reader=self.served_release(self.package("1.4.1")))
        self.assertEqual(result["status"], "ready")
        self.assertEqual(self.state()["version"], "1.4.0")
        self.task("in_progress")
        self.assertEqual(updater.apply_pending(self.profile, self.project)["status"], "deferred")
        self.assertEqual(self.state()["version"], "1.4.0")
        self.task("completed")
        result = updater.apply_pending(self.profile, self.project)
        self.assertEqual(result["status"], "updated", result)
        self.assertEqual(self.state()["version"], "1.4.1")

    def test_modified_verified_cache_is_rejected_before_install(self):
        self.install(self.package("1.4.0"))
        updater.check_now(self.profile, reader=self.served_release(self.package("1.4.1")))
        ready = local.read_json(self.profile / ".trellis-skills/update.json")["ready"]
        self.put(Path(ready["package"]) / "skills/trellis-start/SKILL.md", b"changed after SHA verification")
        result = updater.apply_pending(self.profile, self.project)
        self.assertEqual(result["status"], "failed", "Modified cache was installed without revalidating the verified manifest")
        self.assertEqual(self.state()["version"], "1.4.0")

    def test_real_background_worker_only_checks_and_caches_once_per_invocation(self):
        self.install(self.package("1.4.0"))
        reader = self.served_release(self.package("1.4.1"))
        release = json.loads(reader(updater.API, 1024 * 1024))
        fixture_root = self.base / "release-fixture"
        responses = {}
        for index, url in enumerate([updater.API, *[item["browser_download_url"] for item in release["assets"]]]):
            name = f"response-{index}.bin"
            self.put(fixture_root / name, reader(url, updater.MAX_ZIP))
            responses[url] = {"file": name}
        fixture = fixture_root / "fixture.json"
        self.put(fixture, json.dumps({"responses": responses}).encode())
        self.put(self.profile / ".trellis-skills/TEST-ONLY", b"isolated test profile")
        children = []
        original_popen = subprocess.Popen
        def launch(*args, **kwargs):
            child = original_popen(*args, **kwargs)
            children.append(child)
            return child
        try:
            with mock.patch.object(updater.subprocess, "Popen", side_effect=launch):
                first = updater.background_check(self.profile, "review-start", fixture=fixture)
                second = updater.background_check(self.profile, "review-start", fixture=fixture)
            self.assertEqual(first["status"], "checking-in-background")
            self.assertEqual(second["status"], "already-checked-this-invocation")
            self.assertEqual(len(children), 1)
            self.assertEqual(children[0].wait(timeout=20), 0)
            state = local.read_json(self.profile / ".trellis-skills/update.json")
            self.assertEqual(state["ready"]["version"], "1.4.1")
            self.assertEqual(state["check"]["status"], "ready")
            self.assertEqual(self.state()["version"], "1.4.0")
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)

    def test_competing_worker_preserves_live_check_and_does_not_fetch(self):
        self.install(self.package("1.4.0"))
        entered = self.base / "worker-entered"
        program = """import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import auto_update as updater
def reader(url, limit, **kwargs):
    Path(sys.argv[3]).write_text('entered', encoding='utf-8')
    sys.stdin.readline()
    return json.dumps({'tag_name': 'v1.4.0'}).encode()
print(json.dumps(updater.check_now(Path(sys.argv[2]), reader)))
"""
        owner = subprocess.Popen([sys.executable, "-B", "-c", program, MODULE_SNAPSHOT.name,
                                  str(self.profile), str(entered)], cwd=self.base, env=self.env,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        fixture = self.base / "competing-worker.json"
        self.put(fixture, json.dumps({"responses": {updater.API: {"error": "Competing worker fetched the release"}}}).encode())
        self.put(self.profile / ".trellis-skills/TEST-ONLY", b"isolated test profile")
        children = []
        original_popen = subprocess.Popen
        def launch(*args, **kwargs):
            child = original_popen(*args, **kwargs)
            children.append(child)
            return child
        try:
            deadline = time.monotonic() + 10
            while not entered.exists() and owner.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(entered.exists(), "The owning worker did not enter its controlled request")
            before = local.read_json(self.profile / ".trellis-skills/update.json")["check"]
            with mock.patch.object(updater.subprocess, "Popen", side_effect=launch):
                updater.background_check(self.profile, "competing-turn", fixture=fixture)
            self.assertEqual(len(children), 1)
            self.assertEqual(children[0].wait(timeout=10), 0)
            self.assertEqual(local.read_json(self.profile / ".trellis-skills/update.json")["check"], before)
            output, error = owner.communicate("continue\n", timeout=10)
            self.assertEqual(owner.returncode, 0, error)
            self.assertEqual(json.loads(output)["status"], "current")
            self.assertEqual(local.read_json(self.profile / ".trellis-skills/update.json")["check"]["status"], "current")
            self.assertEqual(self.state()["version"], "1.4.0")
        finally:
            for child in [owner, *children]:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
            for pipe in (owner.stdin, owner.stdout, owner.stderr):
                pipe.close()

    def test_archive_parent_escape_does_not_write_outside_unpack_root(self):
        target = self.base / "unpack"
        target.mkdir()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("trellis-skills-1.4.1/../outside.txt", b"outside")
        with self.assertRaises(ValueError):
            updater.unpack(stream.getvalue(), "1.4.1", target)
        self.assertFalse((self.base / "outside.txt").exists())
        self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
