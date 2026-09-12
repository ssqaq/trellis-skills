import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/trellis-setup/scripts/upgrade_project.py"
SPEC = importlib.util.spec_from_file_location("upgrade_project", SCRIPT)
upgrade_project = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upgrade_project)

WORKFLOW = """# Project workflow
[workflow-state:in_progress]
Project-specific implementation policy.
[/workflow-state:in_progress]
[workflow-state:in_progress-inline]
Do not dispatch agents in inline mode.
[/workflow-state:in_progress-inline]
- 3.5 Wrap-up reminder
#### 3.5 Wrap-up reminder
After the above, remind the user they can run `/finish-work` to wrap up (archive the task, record the session).
Keep the existing release review and private project conventions.
"""


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="trellis-upgrade-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / "project"
        self.workflow = self.project / ".trellis/workflow.md"
        self.workflow.parent.mkdir(parents=True)
        self.workflow.write_text(WORKFLOW, encoding="utf-8")
        self.backups = self.base / "backups"

    def run_upgrade(self, **kwargs):
        return upgrade_project.upgrade(self.project, self.backups, **kwargs)

    def junction(self, link, target):
        if os.name != "nt":
            link.symlink_to(target, target_is_directory=True)
            return
        script = self.base / "make-junction.ps1"
        script.write_text("param($LinkPath, $TargetPath)\nNew-Item -ItemType Junction -Path $LinkPath -Target $TargetPath -ErrorAction Stop | Out-Null\n", encoding="utf-8")
        result = subprocess.run(["pwsh", "-NoProfile", "-File", str(script), "-LinkPath", str(link), "-TargetPath", str(target)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_preserves_project_rules_and_business_files(self):
        agents = self.project / "AGENTS.md"
        custom = "# Team rules\nKeep our payment conventions unchanged.\n"
        agents.write_text(custom, encoding="utf-8")
        preserved = []
        for name in ("app.py", ".trellis/tasks/example/task.json", ".trellis/spec/quality.md", ".trellis/workspace/journal.md"):
            path = self.project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"user-owned\r\n")
            preserved.append(path)
        result = self.run_upgrade()
        self.assertEqual(result["status"], "updated")
        self.assertTrue(agents.read_text(encoding="utf-8").startswith(custom))
        text = self.workflow.read_text(encoding="utf-8")
        self.assertIn("Project-specific implementation policy.", text)
        self.assertIn("Keep the existing release review", text)
        self.assertNotIn("After the above, remind the user", text)
        for path in preserved:
            self.assertEqual(path.read_bytes(), b"user-owned\r\n")

    def test_routes_live_states_without_waiting_for_completed(self):
        self.run_upgrade()
        text = self.workflow.read_text(encoding="utf-8")
        for state in ("in_progress", "in_progress-inline"):
            body = text.split(f"[workflow-state:{state}]")[1].split(f"[/workflow-state:{state}]")[0]
            self.assertIn("Do not wait for another user message or status=completed", body)
            self.assertIn("sub-agents", body)
        self.assertIn("Do not dispatch agents in inline mode.", text)

    def test_state_tags_allow_indentation_and_trailing_spaces(self):
        text = WORKFLOW.replace("[workflow-state:in_progress]\n", "  [workflow-state:in_progress]  \n").replace("[/workflow-state:in_progress]\n", "  [/workflow-state:in_progress]  \n")
        self.workflow.write_text(text, encoding="utf-8")
        self.run_upgrade()
        result = self.workflow.read_text(encoding="utf-8")
        body = result.split("[workflow-state:in_progress]")[1].split("[/workflow-state:in_progress]")[0]
        self.assertIn(upgrade_project.ROUTE_PREFIX, body)
        self.assertEqual(self.run_upgrade()["status"], "current")

    def test_idempotent_and_backups_are_exact(self):
        before = self.workflow.read_bytes()
        first = self.run_upgrade()
        after = self.workflow.read_bytes()
        self.assertEqual(Path(first["backups"][0]).read_bytes(), before)
        self.assertEqual(self.run_upgrade()["status"], "current")
        self.assertEqual(after, self.workflow.read_bytes())
        self.assertEqual(len(list(self.backups.rglob("*.bak"))), 1)

    def test_saved_workflow_variants_are_upgraded(self):
        variant = self.project / ".trellis/workflows/custom.md"
        variant.parent.mkdir()
        variant.write_text(WORKFLOW + "\nOnly use our custom runner.\n", encoding="utf-8")
        self.run_upgrade()
        text = variant.read_text(encoding="utf-8")
        self.assertIn(upgrade_project.START, text)
        self.assertIn("Only use our custom runner.", text)

    def test_bom_and_crlf_preserved(self):
        raw = b"\xef\xbb\xbf" + WORKFLOW.replace("\n", "\r\n").encode("utf-8")
        self.workflow.write_bytes(raw)
        self.run_upgrade()
        result = self.workflow.read_bytes()
        self.assertTrue(result.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", result.replace(b"\r\n", b""))
        self.assertEqual(self.run_upgrade()["status"], "current")

    def test_check_does_not_write(self):
        before = self.workflow.read_bytes()
        self.assertEqual(self.run_upgrade(check=True)["status"], "needs-upgrade")
        self.assertEqual(before, self.workflow.read_bytes())
        self.assertFalse((self.project / "AGENTS.md").exists())
        self.assertFalse(self.backups.exists())

    def test_malformed_markers_leave_all_files_untouched(self):
        agents = self.project / "AGENTS.md"
        agents.write_text(upgrade_project.START + "\nunfinished custom edit", encoding="utf-8")
        before = self.workflow.read_bytes()
        with self.assertRaises(ValueError):
            self.run_upgrade()
        self.assertEqual(before, self.workflow.read_bytes())
        self.assertFalse(self.backups.exists())

    def test_unknown_text_is_preserved_with_explicit_closeout_supplement(self):
        self.workflow.write_text("# Custom workflow\nRun our own lint before commit.\n", encoding="utf-8")
        self.run_upgrade()
        self.assertTrue(self.workflow.read_text(encoding="utf-8").startswith("# Custom workflow\nRun our own lint before commit.\n"))

    def test_requires_initialized_project(self):
        self.workflow.unlink()
        with self.assertRaises(ValueError):
            self.run_upgrade()
        self.assertFalse((self.project / "AGENTS.md").exists())

    def test_registration_preserves_offline_projects_and_deduplicates(self):
        registry = self.base / "registry.json"
        registry.write_text(json.dumps({"version": 1, "projects": [str(self.base / "offline")]}), encoding="utf-8")
        upgrade_project.register(self.project, registry)
        upgrade_project.register(self.project, registry)
        self.assertEqual(len(json.loads(registry.read_text(encoding="utf-8"))["projects"]), 2)

    def test_project_skill_refresh_after_init_preserves_other_skills(self):
        source = self.base / "source/trellis-start"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("current skill", encoding="utf-8")
        target = self.project / ".agents/skills"
        (target / "trellis-start").mkdir(parents=True)
        (target / "trellis-start/SKILL.md").write_text("old init template", encoding="utf-8")
        (target / "unrelated").mkdir()
        (target / "unrelated/SKILL.md").write_text("user skill", encoding="utf-8")
        upgrade_project.sync_skills(self.project, source.parent)
        self.assertEqual((target / "trellis-start/SKILL.md").read_text(encoding="utf-8"), "current skill")
        self.assertEqual((target / "unrelated/SKILL.md").read_text(encoding="utf-8"), "user skill")

    def test_global_entry_is_scoped_preserves_user_rules_and_is_idempotent(self):
        profile = self.base / "profile"
        agents = profile / ".codex/AGENTS.md"
        agents.parent.mkdir(parents=True)
        original = b"# Existing user preferences\r\nPreserve my conventions.\r\n"
        agents.write_bytes(original)
        result = upgrade_project.upgrade_global_rules(profile, self.backups)
        self.assertEqual(result["status"], "updated")
        self.assertTrue(agents.read_bytes().startswith(original))
        self.assertEqual(Path(result["backups"][0]).read_bytes(), original)
        self.assertIn("Other projects", agents.read_text(encoding="utf-8"))
        self.assertEqual(upgrade_project.upgrade_global_rules(profile, self.backups)["status"], "current")
        upgrade_project.remove_global_rules(profile, self.backups)
        self.assertEqual(agents.read_bytes(), original)

    def test_real_installer_updates_global_legacy_and_registered_project(self):
        profile = self.base / "profile"
        for relative in [".agents/skills/trellis-start", ".codex/skills/trellis-start", ".agents/skills/unrelated"]:
            path = profile / relative
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text("old", encoding="utf-8")
        registry = profile / ".trellis-skills/projects.json"
        registry.parent.mkdir()
        registry.write_text(json.dumps({"version": 1, "projects": [str(self.project)]}), encoding="utf-8")
        env = dict(os.environ, USERPROFILE=str(profile), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(["pwsh", "-NoProfile", "-File", str(SCRIPT.parents[3] / "install.ps1")], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        source = SCRIPT.parents[2] / "trellis-start/SKILL.md"
        for relative in [".agents/skills/trellis-start/SKILL.md", ".codex/skills/trellis-start/SKILL.md"]:
            self.assertEqual((profile / relative).read_bytes(), source.read_bytes())
        self.assertFalse(list((profile / ".agents/skills").rglob("*.pyc")))
        self.assertEqual((profile / ".agents/skills/unrelated/SKILL.md").read_text(encoding="utf-8"), "old")
        self.assertIn(upgrade_project.GLOBAL_START, (profile / ".codex/AGENTS.md").read_text(encoding="utf-8"))
        self.assertIn(upgrade_project.START, self.workflow.read_text(encoding="utf-8"))
        result = subprocess.run(["pwsh", "-NoProfile", "-File", str(SCRIPT.parents[3] / "uninstall.ps1")], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(list((profile / ".agents/skills").glob("trellis-*")))
        self.assertFalse(list((profile / ".codex/skills").glob("trellis-*")))
        self.assertTrue((profile / ".agents/skills/unrelated/SKILL.md").is_file())
        self.assertNotIn(upgrade_project.GLOBAL_START, (profile / ".codex/AGENTS.md").read_text(encoding="utf-8"))

    def test_uninstall_rejects_parent_junction_without_deleting_external_files(self):
        profile = self.base / "profile"
        (profile / ".agents").mkdir(parents=True)
        outside = self.base / "outside"
        (outside / "trellis-start").mkdir(parents=True)
        sentinel = outside / "trellis-start/SKILL.md"
        sentinel.write_text("do not touch", encoding="utf-8")
        self.junction(profile / ".agents/skills", outside)
        env = dict(os.environ, USERPROFILE=str(profile))
        result = subprocess.run(["pwsh", "-NoProfile", "-File", str(SCRIPT.parents[3] / "uninstall.ps1")], env=env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not touch")

    def test_failed_skill_sync_leaves_no_ready_markers(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "SKILL.md").write_text("keep", encoding="utf-8")
        target = self.project / ".agents/skills"
        target.mkdir(parents=True)
        self.junction(target / "trellis-start", outside)
        registry = self.base / "registry.json"
        result = subprocess.run(["python", "-B", str(SCRIPT), "--project-root", str(self.project), "--backup-root", str(self.backups), "--registry-path", str(registry), "--sync-skills", "--register"], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(upgrade_project.START, self.workflow.read_text(encoding="utf-8"))
        self.assertFalse((self.project / "AGENTS.md").exists())
        self.assertFalse(registry.exists())
        self.assertEqual((outside / "SKILL.md").read_text(encoding="utf-8"), "keep")

    def test_relative_registration_uses_powershell_location(self):
        registry = self.base / "registry.json"
        script = self.base / "register-relative.ps1"
        script.write_text("param($Project, $Sync, $Registry)\nSet-Location -LiteralPath $Project\n& $Sync -ProjectRoot '.' -RegistryPath $Registry\n", encoding="utf-8")
        result = subprocess.run(["pwsh", "-NoProfile", "-File", str(script), "-Project", str(self.project), "-Sync", str(SCRIPT.parents[3] / "sync-local-skills.ps1"), "-Registry", str(registry)], cwd=self.base, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(registry.read_text(encoding="utf-8-sig"))["projects"], [str(self.project)])
        self.assertIn(upgrade_project.START, self.workflow.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
