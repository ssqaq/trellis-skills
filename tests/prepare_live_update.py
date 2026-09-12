"""Prepare disposable real-Codex projects and an explicit offline Release transport."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills/trellis-setup/scripts"))
import local_install as local
import auto_update


def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    root = Path(tempfile.mkdtemp(prefix="trellis-live-update-")).resolve()
    profile = root / "profile"
    source = root / "old-package"
    new_source = root / "new-package"
    for name, raw in local.package_files(REPO).items():
        for package in (source, new_source):
            destination = package / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
    for package, version in ((source, "1.4.0"), (new_source, "1.4.1")):
        put(package / "VERSION", version + "\n")
        put(package / "skills/trellis-setup/VERSION", version + "\n")
    put(new_source / "skills/trellis-start/fixture-version.txt", "Local simulation of a newer stable release.\n")
    put(profile / ".trellis-skills/TEST-ONLY", "Only this disposable profile may use fixture responses.\n")
    release_dir = root / "release"
    release_dir.mkdir()
    filename = "trellis-skills-1.4.1.zip"
    with zipfile.ZipFile(release_dir / filename, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in new_source.rglob("*"):
            if path.is_file():
                archive.write(path, "trellis-skills-1.4.1/" + path.relative_to(new_source).as_posix())
    digest = hashlib.sha256((release_dir / filename).read_bytes()).hexdigest()
    put(release_dir / (filename + ".sha256"), digest + "  " + filename + "\n")
    base_url = "https://github.com/ssqaq/trellis-skills/releases/download/v1.4.1/"
    release = {"tag_name": "v1.4.1", "draft": False, "prerelease": False, "assets": [
        {"name": filename, "browser_download_url": base_url + filename, "digest": "sha256:" + digest},
        {"name": filename + ".sha256", "browser_download_url": base_url + filename + ".sha256"}]}
    local.write_json(release_dir / "release.json", release)
    fixture = release_dir / "responses.json"
    local.write_json(fixture, {"responses": {auto_update.API: {"file": "release.json"},
        base_url + filename: {"file": filename}, base_url + filename + ".sha256": {"file": filename + ".sha256"}}})
    projects = [root / "format-project", root / "parse-project"]
    for project in projects:
        project.mkdir()
        run(["git", "init", "-b", "main"], project)
        run(["git", "config", "user.name", "Trellis Fixture"], project)
        run(["git", "config", "user.email", "fixture@example.invalid"], project)
        run(["git", "config", "commit.gpgsign", "false"], project)
        run(["pwsh", "-NoProfile", "-Command", "trellis init --codex --yes --user codex"], project)
        config = project / ".trellis/config.yaml"
        put(config, config.read_text(encoding="utf-8") + "\ncodex:\n  dispatch_mode: inline\n")
        put(project / ".gitignore", "__pycache__/\n*.pyc\n")
        function = "format_seconds" if project == projects[0] else "parse_duration"
        put(project / "duration.py", f"def {function}(value):\n    raise NotImplementedError\n")
        put(project / "README.md", "# Duration utility\nImplement the requested conversion with documented examples.\n")
        put(project / "quality_check.py", "import ast\nfrom pathlib import Path\nimport subprocess, sys\nfor path in Path('.').glob('*.py'):\n    ast.parse(path.read_text(encoding='utf-8'))\nraise SystemExit(subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v']).returncode)\n")
        (project / "tests").mkdir()
        put(project / "tests/test_duration.py", "import unittest\nfrom duration import " + function + "\n\nclass DurationTests(unittest.TestCase):\n    def test_example(self):\n" +
            ("        self.assertEqual(format_seconds(62), '1m 2s')\n" if function == "format_seconds" else "        self.assertEqual(parse_duration('1h 2m 3s'), 3723)\n"))
        original = (project / "AGENTS.md").read_text(encoding="utf-8")
        binding = f"""# Isolated fixture environment

This project uses a disposable Codex profile: `{profile}`.
For all Trellis update instructions, `<user-profile>` means that path, not the
machine's real USERPROFILE. Every auto_update.py invocation must include
`--profile \"{profile}\"`. For check/worker commands also pass
`--release-fixture \"{fixture}\"`; this is the local test transport.
Do not touch real global skills or business projects outside this fixture.
The required complete project check is `python -B quality_check.py`.
Use real Trellis task/archive/journal scripts. Local task, code, archive and
journal commits are authorized. No remote or deployment is involved.

"""
        put(project / "AGENTS.md", binding + original)
    result = local.install(source, profile, project_roots=projects)
    # B represents an already-started task while A performs its ordinary work.
    task_output = run([sys.executable, "-B", ".trellis/scripts/task.py", "create", "Implement duration parser", "--slug", "duration-parser"], projects[1])
    task = next((projects[1] / ".trellis/tasks").glob("*-duration-parser"))
    data = local.read_json(task / "task.json")
    data["status"] = "in_progress"
    local.write_json(task / "task.json", data)
    put(task / "prd.md", "# Duration parser\nImplement parse_duration: h/m/s integer units in order, reject invalid/duplicate units and negative input; document examples and test all boundaries. Authorized for implementation and local commits.\n")
    for project in projects:
        run(["git", "add", "."], project)
        run(["git", "commit", "-m", "Prepare isolated duration project"], project)
    result = {"root": str(root), "profile": str(profile), "projects": list(map(str, projects)), "release_fixture": str(fixture),
              "simulated_versions": ["1.4.0", "1.4.1"], "source_sha256": {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in (REPO / "skills/trellis-setup/scripts").glob("*.py")}}
    local.write_json(root / "fixture.json", result)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
