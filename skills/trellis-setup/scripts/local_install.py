"""Versioned, reversible installation shared by manual and automatic updates."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import time

import upgrade_project as migration


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value)
    if not match:
        raise ValueError("Expected a stable major.minor.patch version")
    return tuple(map(int, match.groups()))


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else default


def path_key(path) -> str:
    return os.path.normcase(os.path.abspath(path))


def write_json(path: Path, value) -> None:
    migration.atomic_write(path, json.dumps(value, ensure_ascii=True, indent=2).encode())


def safe(path: Path) -> Path:
    path = path.absolute()
    if migration.has_link(path, path.anchor and Path(path.anchor) or path):
        raise ValueError(f"Linked managed path: {path}")
    return path


@contextmanager
def lock(path: Path, timeout: float = 0):
    """Kernel locks are released even if the owning process is terminated."""
    safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    handle.seek(0, 2)
    if not handle.tell():
        handle.write(b"0")
        handle.flush()
    deadline = time.monotonic() + timeout
    acquired = False
    try:
        while True:
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise BlockingIOError(f"Another Trellis operation owns {path.name}")
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def package_files(source: Path) -> dict[str, bytes]:
    source = safe(source)
    files = {}
    for path in sorted((source / "skills").rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        safe(path)
        if path.is_file():
            files[path.relative_to(source).as_posix()] = path.read_bytes()
    for name in ("VERSION", "install.ps1", "sync-local-skills.ps1", "uninstall.ps1"):
        files[name] = safe(source / name).read_bytes()
    version_tuple(files["VERSION"].decode("utf-8-sig").strip())
    for name in ("trellis-start", "trellis-continue", "trellis-finish-work", "trellis-check", "trellis-setup"):
        if f"skills/{name}/SKILL.md" not in files:
            raise ValueError(f"Incomplete package: {name}")
    if "skills/trellis-setup/scripts/upgrade_project.py" not in files:
        raise ValueError("Package is missing its migration helper")
    return files


def save_package(source: Path, state_dir: Path) -> tuple[Path, str, dict]:
    files = package_files(source)
    version = files["VERSION"].decode("utf-8-sig").strip()
    manifest = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    destination = safe(state_dir / "packages" / f"{version}-{digest[:16]}")
    for name, raw in files.items():
        path = safe(destination / name)
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError("A retained package was modified")
        else:
            migration.atomic_write(path, raw)
    write_json(destination / "manifest.json", manifest)
    return destination, version, files


def verify_package(package: Path) -> None:
    files = package_files(package)
    actual = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    expected = read_json(safe(package / "manifest.json"))
    digest = hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest()
    version = files["VERSION"].decode("utf-8-sig").strip()
    if actual != expected or package.name != f"{version}-{digest[:16]}":
        raise ValueError("Retained package integrity verification failed")


def busy(root: Path) -> bool:
    """Unarchived execution/paused/unknown records must not be guessed idle."""
    selected = set()
    for session in (root / ".trellis/.runtime/sessions").glob("*.json"):
        try:
            reference = read_json(safe(session), {}).get("current_task")
            if reference:
                selected.add(str(reference).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1])
        except (ValueError, AttributeError):
            return True
    marker = root / ".trellis/.current-task"
    if marker.exists():
        reference = safe(marker).read_text(encoding="utf-8-sig").strip()
        if reference:
            selected.add(reference.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1])
    tasks = root / ".trellis/tasks"
    if tasks.exists():
        safe(tasks)
        for folder in tasks.iterdir():
            if folder.name == "archive" or not folder.is_dir():
                continue
            safe(folder)
            record = safe(folder / "task.json")
            if record.exists():
                try:
                    data = read_json(record)
                    # trellis init creates this in_progress template without starting work.
                    # Preserve it as-is, but never ignore a selected or worked-on bootstrap.
                    if (folder.name == "00-bootstrap-guidelines" and folder.name not in selected
                            and data.get("id") == "00-bootstrap-guidelines"
                            and data.get("status") == "in_progress"
                            and str(data.get("notes", "")).startswith("First-time setup task created by trellis init")
                            and not any(data.get(key) for key in ("branch", "worktree_path", "commit", "pr_url", "meta"))):
                        continue
                    if data.get("status") not in ("planning", "completed", "done", "cancelled", "canceled"):
                        return True
                except (ValueError, AttributeError):
                    return True
    if marker.exists():
        safe(marker)
        selected = marker.read_text(encoding="utf-8-sig").strip()
        if selected:
            task = root / selected / "task.json"
            # A missing selected task is an interrupted workflow, not proof of idle.
            if not task.is_file():
                return True
    return False


class Transaction:
    """Preflight every managed file, then journal recoverable writes."""
    def __init__(self, state_dir: Path, backup_root: Path):
        self.state_dir = state_dir
        self.backup_root = backup_root
        self.changes = {}
        self.written = []

    def put(self, path: Path, raw: bytes | None):
        path = safe(path)
        old = path.read_bytes() if path.exists() else None
        if old != raw:
            self.changes[str(path)] = (old, raw)

    def capture(self, root, changes, backup_root, check):
        for path, old, new, existed in changes:
            self.put(path, new)
        return {"status": "prepared"}

    def apply(self):
        journal = self.state_dir / "transaction.json"
        records = []
        for name, (old, new) in self.changes.items():
            path = safe(Path(name))
            if (path.read_bytes() if path.exists() else None) != old:
                raise RuntimeError(f"Managed file changed during preparation: {path}")
            backup = None
            if old is not None:
                identity = hashlib.sha256(name.encode()).hexdigest()[:20]
                backup = safe(self.backup_root / identity / (hashlib.sha256(old).hexdigest() + ".bak"))
                if not backup.exists():
                    migration.atomic_write(backup, old)
                    write_json(backup.with_suffix(".json"), {"original": name})
            records.append({"path": name, "backup": str(backup) if backup else None,
                            "new_sha": hashlib.sha256(new).hexdigest() if new is not None else None})
        write_json(journal, {"records": records, "applied": 0, "committed": False})
        try:
            for index, (name, (old, new)) in enumerate(self.changes.items()):
                path = safe(Path(name))
                if (path.read_bytes() if path.exists() else None) != old:
                    raise RuntimeError(f"Managed file changed during installation: {path}")
                # Mark before writing so a crash between write and journal update is recoverable.
                write_json(journal, {"records": records, "applied": index + 1, "committed": False})
                if new is None:
                    path.unlink(missing_ok=True)
                else:
                    migration.atomic_write(path, new)
                self.written.append(name)
                if (path.read_bytes() if path.exists() else None) != new:
                    raise RuntimeError(f"Installed file verification failed: {path}")
            write_json(journal, {"records": records, "applied": len(records), "committed": True})
        except BaseException:
            recover(self.state_dir)
            raise


def recover(state_dir: Path):
    journal = read_json(state_dir / "transaction.json", {})
    if not journal or journal.get("committed"):
        return
    conflicts = []
    for record in reversed(journal["records"][:journal["applied"]]):
        path = safe(Path(record["path"]))
        old = safe(Path(record["backup"])).read_bytes() if record["backup"] else None
        now = path.read_bytes() if path.exists() else None
        if now == old:
            continue
        digest = hashlib.sha256(now).hexdigest() if now is not None else None
        if digest != record["new_sha"]:
            conflicts.append(str(path))
            continue
        if old is None:
            path.unlink(missing_ok=True)
        else:
            migration.atomic_write(path, old)
    if conflicts:
        raise RuntimeError("Rollback left concurrent edits intact; repair required: " + ", ".join(conflicts))
    write_json(state_dir / "transaction.json", {"records": [], "applied": 0, "committed": True})


def registered(registry: Path, extra=()) -> list[Path]:
    data = read_json(registry, {"projects": []})
    values = data.get("projects", []) if isinstance(data, dict) else data
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError("Invalid registered project list")
    result = {}
    for value in [*values, *map(str, extra)]:
        path = Path(value).absolute()
        result[os.path.normcase(str(path))] = path
    return list(result.values())


def install(source: Path, profile: Path, *, global_install=True, defer_active=True,
            project_roots=(), registry_path=None, backup_root=None, automatic=False) -> dict:
    profile = safe(profile)
    state_dir = safe(profile / ".trellis-skills")
    registry = safe(registry_path or state_dir / "projects.json")
    if registry_path is not None:
        state_dir = registry.parent
    backups = safe(backup_root or registry.parent / "backups")
    with lock(state_dir / "install.lock"):
        if automatic and (state_dir / "disabled").exists():
            raise ValueError("Automatic updates were disabled")
        recover(state_dir)
        old_state = read_json(state_dir / "installed.json", {})
        package, version, files = save_package(source, state_dir)
        if global_install and old_state.get("version") and version_tuple(version) < version_tuple(old_state["version"]):
            raise ValueError("Refusing to downgrade the installed skill package")
        roots = registered(registry, project_roots)
        discovery = migration.discover_projects(roots)
        projects = {str(Path(p)): Path(p) for p in discovery["Projects"]}
        for target in discovery["Skills"]:
            root = Path(target).parents[1]
            projects.setdefault(str(root), root)
        missing = [str(p) for p in roots if not p.exists()]
        project_states = dict(old_state.get("projects", {}))
        # Previously discovered children are retained even when currently offline.
        for name in project_states:
            path = Path(name)
            if any(path == root or root in path.parents for root in roots) and not path.exists():
                missing.append(name)
        current_files = {name.removeprefix("skills/"): raw for name, raw in files.items() if name.startswith("skills/")}
        old_files = old_state.get("managed_files", [])
        transaction = Transaction(state_dir, backups)

        def copy_skills(destination, content=current_files, previous=old_files):
            safe(destination)
            for name in [*content, *previous]:
                parts = PurePosixPath(name).parts
                if (not parts or not parts[0].startswith("trellis-") or ".." in parts
                        or "\\" in name or ":" in name or PurePosixPath(name).is_absolute()):
                    raise ValueError("Invalid managed skill manifest path")
            for name, raw in content.items():
                transaction.put(destination / name, raw)
            for name in set(previous) - set(content):
                # Delete only files recorded by our installer, never unknown user files.
                transaction.put(destination / name, None)

        original_apply = migration.apply_changes
        migration.apply_changes = transaction.capture
        pending = []
        updated = []
        try:
            for name, project in projects.items():
                old_key = next((key for key in project_states if path_key(key) == path_key(name)), name)
                previous = project_states.pop(old_key, {})
                if defer_active and busy(project):
                    pinned = previous.get("skills_source")
                    if not pinned:
                        # Pin the exact global files before changing globals. Existing local copies stay untouched.
                        pin = state_dir / "pins" / hashlib.sha256(name.encode()).hexdigest()[:20]
                        for old_source in (profile / ".codex/skills", profile / ".agents/skills",
                                           project / ".codex/skills", project / ".agents/skills"):
                            for skill in old_source.glob("trellis-*"):
                                for item in skill.rglob("*"):
                                    safe(item)
                                    if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc":
                                        transaction.put(pin / item.relative_to(old_source), item.read_bytes())
                        pinned = str(pin)
                    project_states[name] = {**previous, "version": previous.get("version", old_state.get("version", "unknown")),
                                           "pending_version": version, "reason": "busy", "skills_source": pinned}
                    pending.append({"project": name, "reason": "busy"})
                    continue
                targets = [Path(t) for t in discovery["Skills"] if Path(t).parents[1] == project]
                for target in targets:
                    copy_skills(target, previous=previous.get("managed_files", old_files))
                if (project / ".trellis/workflow.md").is_file():
                    migration.upgrade(project, backups)
                project_states[name] = {"version": version, "skills_source": str(package / "skills"),
                                        "managed_files": list(current_files)}
                updated.append(name)
            for name in sorted(set(missing)):
                project_states[name] = {**project_states.get(name, {}), "pending_version": version, "reason": "offline"}
                pending.append({"project": name, "reason": "offline"})
            if global_install:
                copy_skills(profile / ".agents/skills")
                legacy = profile / ".codex/skills"
                if legacy.exists() and any(legacy.glob("trellis-*")):
                    copy_skills(legacy)
                migration.upgrade_global_rules(profile, backups)
        finally:
            migration.apply_changes = original_apply
        if project_roots:
            transaction.put(registry, json.dumps({"version": 1, "projects": list(map(str, roots))}, ensure_ascii=True, indent=2).encode())
        new_state = {**old_state, "projects": project_states}
        if global_install:
            new_state.update(version=version, package=str(package), managed_files=list(current_files))
        transaction.put(state_dir / "installed.json", json.dumps(new_state, ensure_ascii=True, indent=2).encode())
        if global_install and not automatic:
            transaction.put(state_dir / "disabled", None)
        if defer_active and any(busy(projects[name]) for name in updated):
            raise RuntimeError("A project started work during installation preparation; retry after its closeout")
        transaction.apply()
        return {"status": "updated" if transaction.changes else "current", "version": version,
                "global_updated": global_install, "projects_updated": updated, "pending_projects": pending,
                "changed_files": len(transaction.changes)}


def project_source(profile: Path, project: Path) -> str:
    state = read_json(profile / ".trellis-skills/installed.json", {})
    item = next((value for key, value in state.get("projects", {}).items() if path_key(key) == path_key(project)), {})
    source = item.get("skills_source")
    return source or str(profile / ".agents/skills")
