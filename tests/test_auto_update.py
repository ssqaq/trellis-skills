"""Release selection, lifecycle, and isolated installer integration cases."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock
import zipfile

import test_auto_update_review as fixtures

local, updater = fixtures.local, fixtures.updater


class LifecycleTests(unittest.TestCase):
    setUp = fixtures.AutoUpdateReviewTests.setUp
    put = staticmethod(fixtures.AutoUpdateReviewTests.put)
    package = fixtures.AutoUpdateReviewTests.package
    install = fixtures.AutoUpdateReviewTests.install
    state = fixtures.AutoUpdateReviewTests.state
    task = fixtures.AutoUpdateReviewTests.task
    served_release = fixtures.AutoUpdateReviewTests.served_release

    def test_current_old_and_prerelease_do_not_download(self):
        self.install(self.package("1.4.0"))
        for tag, prerelease, draft in (("v1.4.0", False, False), ("v1.3.4", False, False),
                                        ("v1.5.0", True, False), ("v1.5.0", False, True),
                                        ("v1.5.0-beta.1", False, False)):
            with self.subTest(tag=tag, prerelease=prerelease, draft=draft):
                reader = mock.Mock(return_value=json.dumps({"tag_name": tag, "prerelease": prerelease, "draft": draft}).encode())
                self.assertEqual(updater.check_now(self.profile, reader)["status"], "current")
                self.assertEqual(reader.call_count, 1)
                self.assertEqual(self.state()["version"], "1.4.0")

    def test_semver_numeric_order_and_foreign_asset_rejection(self):
        self.assertGreater(local.version_tuple("1.10.0"), local.version_tuple("1.9.99"))
        with self.assertRaises(ValueError):
            updater.release_candidate({"tag_name": "v1.5.0", "assets": [
                {"name": "trellis-skills-1.5.0.zip", "browser_download_url": "https://example.com/package.zip"}]}, "1.4.0")

    def test_rate_limit_retains_current_installation(self):
        self.install(self.package("1.4.0"))
        before = self.state()
        reader = mock.Mock(side_effect=OSError("HTTP 403 rate limit"))
        result = updater.check_now(self.profile, reader)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.state(), before)

    def test_archive_version_mismatch_and_case_collision(self):
        source = self.package("1.4.2")
        for duplicate in (False, True):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as archive:
                for path in source.rglob("*"):
                    if path.is_file():
                        archive.writestr("trellis-skills-1.4.1/" + path.relative_to(source).as_posix(), path.read_bytes())
                if duplicate:
                    archive.writestr("trellis-skills-1.4.1/version", b"1.4.1")
            with self.assertRaises(ValueError):
                updater.unpack(stream.getvalue(), "1.4.1", self.base / ("unpacked-" + str(duplicate)))

    def test_global_only_busy_project_uses_old_retained_package(self):
        target = self.project / ".agents/skills/trellis-start/SKILL.md"
        target.unlink()
        target.parent.rmdir()
        target.parent.parent.rmdir()
        target.parent.parent.parent.rmdir()
        self.install(self.package("1.4.0"))
        self.task("in_progress")
        self.install(self.package("1.4.1"))
        selected = Path(local.project_source(self.profile, self.project))
        self.assertEqual((selected / "trellis-start/SKILL.md").read_bytes(), b"trellis-start 1.4.0")
        self.assertEqual(self.state()["version"], "1.4.1")
        self.assertFalse((self.project / ".agents").exists())
        self.task("completed")
        updater.apply_pending(self.profile, self.project)
        self.assertEqual(self.state()["projects"][str(self.project)]["version"], "1.4.1")

    def test_disable_prevents_worker_and_automatic_reinstallation(self):
        source = self.package("1.4.0")
        self.install(source)
        self.put(self.profile / ".trellis-skills/disabled", b"disabled")
        self.assertEqual(updater.background_check(self.profile, "turn-1")["status"], "disabled")
        self.assertEqual(updater.check_now(self.profile, mock.Mock())["status"], "disabled")
        self.assertEqual(updater.apply_pending(self.profile, self.project)["status"], "disabled")
        with self.assertRaises(ValueError):
            local.install(source, self.profile, automatic=True)
        self.install(source)
        self.assertFalse((self.profile / ".trellis-skills/disabled").exists())

    def test_finished_task_does_not_wait_indefinitely_for_download(self):
        self.install(self.package("1.4.0"))
        local.write_json(self.profile / ".trellis-skills/update.json", {"check": {"status": "checking"}})
        started = time.monotonic()
        result = updater.apply_pending(self.profile, self.project, wait_seconds=0.15)
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(result["status"], "current")

    def test_new_task_starting_during_preflight_aborts_without_overwrite(self):
        self.install(self.package("1.4.0"))
        old = self.state()
        original = local.busy
        calls = 0
        def changing(root):
            nonlocal calls
            calls += 1
            return calls > 1 or original(root)
        with mock.patch.object(local, "busy", side_effect=changing):
            with self.assertRaises(RuntimeError):
                self.install(self.package("1.4.1"))
        self.assertEqual(self.state(), old)

    def test_custom_registry_does_not_write_global_install_state(self):
        source = self.package("1.4.0")
        registry = self.base / "custom/registry.json"
        local.install(source, self.profile, global_install=False, project_roots=[self.project], registry_path=registry)
        self.assertFalse((self.profile / ".trellis-skills/installed.json").exists())
        self.assertTrue((registry.parent / "installed.json").is_file())

    def test_test_transport_requires_explicit_temporary_profile_marker(self):
        fixture = self.base / "fixture.json"
        self.put(fixture, b'{"responses":{}}')
        with self.assertRaises(ValueError):
            updater.fixture_fetch(self.profile, fixture)

    def test_pause_or_invalid_task_state_stays_pending(self):
        self.install(self.package("1.4.0"))
        for status in ("paused", "in_progress", "interrupted", "unknown"):
            self.task(status)
            self.assertEqual(updater.apply_pending(self.profile, self.project)["status"], "deferred")
        self.put(self.project / ".trellis/tasks/active/task.json", b"bad-json")
        self.assertTrue(local.busy(self.project))

    def test_each_new_invocation_checks_even_immediately_after_previous_one(self):
        self.install(self.package("1.4.0"))
        with mock.patch.object(updater.subprocess, "Popen") as launch:
            launch.return_value.pid = 123
            self.assertEqual(updater.background_check(self.profile, "first")["status"], "checking-in-background")
            self.assertEqual(updater.background_check(self.profile, "first")["status"], "already-checked-this-invocation")
            self.assertEqual(updater.background_check(self.profile, "second")["status"], "checking-in-background")
            self.assertEqual(launch.call_count, 2)


if __name__ == "__main__":
    unittest.main()
