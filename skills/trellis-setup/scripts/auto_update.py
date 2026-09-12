"""Check official releases in a short-lived worker; install only at task boundaries."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid
import zipfile

import local_install as local

REPO = "ssqaq/trellis-skills"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
MAX_ZIP = 128 * 1024 * 1024
MAX_UNPACKED = 256 * 1024 * 1024


def state_dir(profile):
    return local.safe(profile / ".trellis-skills")


def state_change(profile, change):
    root = state_dir(profile)
    with local.lock(root / "state.lock", timeout=3):
        value = local.read_json(root / "update.json", {})
        change(value)
        local.write_json(root / "update.json", value)
        return value


def fetch(url: str, limit: int, timeout=10, deadline=None) -> bytes:
    if deadline is None:
        deadline = time.monotonic() + 20
    request = Request(url, headers={"User-Agent": "trellis-skills-auto-update", "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=timeout) as response:
        final = urlparse(response.url)
        if final.scheme != "https" or final.hostname not in (
                "api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"):
            raise ValueError("Unexpected release download redirect")
        chunks, size = [], 0
        while True:
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError("Release download timed out")
            chunk = response.read(min(65536, limit + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ValueError("Release response exceeds the size limit")
            chunks.append(chunk)
        return b"".join(chunks)


def release_candidate(release: dict, current: str):
    if release.get("draft") or release.get("prerelease"):
        return None
    tag = release.get("tag_name", "")
    try:
        version = ".".join(map(str, local.version_tuple(tag)))
    except (ValueError, TypeError):
        return None
    if local.version_tuple(version) <= local.version_tuple(current):
        return None
    filename = f"trellis-skills-{version}.zip"
    assets = release.get("assets", [])
    selected = {}
    for name in (filename, filename + ".sha256"):
        matches = [asset for asset in assets if asset.get("name") == name and asset.get("state", "uploaded") == "uploaded"]
        if len(matches) != 1:
            raise ValueError("The official release is missing a unique package or checksum")
        asset = matches[0]
        expected_url = f"https://github.com/{REPO}/releases/download/{tag}/{name}"
        if asset.get("browser_download_url") != expected_url:
            raise ValueError("The release asset URL does not belong to the official repository")
        selected[name] = asset
    return version, selected


def unpack(data: bytes, version: str, target: Path):
    import io
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if sum(item.file_size for item in entries) > MAX_UNPACKED or len(entries) > 10000:
            raise ValueError("Release archive is too large")
        seen = set()
        prefix = f"trellis-skills-{version}"
        for item in entries:
            name = item.filename
            parts = PurePosixPath(name).parts
            if (not parts or parts[0] != prefix or "\\" in name or ":" in name
                    or any(part in ("..", ".") or part.endswith((".", " ")) for part in parts)
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Unsafe release archive path")
            key = name.rstrip("/").casefold()
            if key in seen:
                raise ValueError("Duplicate archive destination")
            seen.add(key)
        for item in entries:
            relative = PurePosixPath(item.filename).parts[1:]
            path = local.safe(target.joinpath(*relative))
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                local.migration.atomic_write(path, archive.read(item))
    files = local.package_files(target)
    if files["VERSION"].decode("utf-8-sig").strip() != version:
        raise ValueError("The package VERSION does not match the release tag")
    for script in ("auto_update.py", "local_install.py"):
        if f"skills/trellis-setup/scripts/{script}" not in files:
            raise ValueError("The update package has no compatible updater")


def fixture_fetch(profile: Path, fixture: Path):
    """Explicit offline transport for isolated end-to-end tests, never project-controlled."""
    profile = profile.resolve()
    temp = Path(tempfile.gettempdir()).resolve()
    if not profile.is_relative_to(temp) or not (profile / ".trellis-skills/TEST-ONLY").is_file():
        raise ValueError("Release fixtures require an explicitly marked temporary test profile")
    payload = local.read_json(fixture)
    urls = payload["responses"]

    def read(url, limit, **kwargs):
        entry = urls[url]
        if "error" in entry:
            raise OSError(entry["error"])
        path = (fixture.parent / entry["file"]).resolve()
        if not path.is_relative_to(fixture.parent.resolve()):
            raise ValueError("Fixture response escapes its fixture directory")
        raw = path.read_bytes()
        if len(raw) > limit:
            raise ValueError("Fixture exceeds response limit")
        return raw
    return read


def check_now(profile: Path, reader=fetch) -> dict:
    root = state_dir(profile)
    with local.lock(root / "check.lock"):
        if (root / "disabled").exists():
            return {"status": "disabled"}
        current = local.read_json(root / "installed.json", {}).get("version")
        if not current:
            raise ValueError("Install the current skill package once before enabling automatic updates")
        state_change(profile, lambda state: state.update(check={"status": "checking", "pid": os.getpid()}))
        try:
            release = json.loads(reader(API, 1024 * 1024))
            candidate = release_candidate(release, current)
            if candidate is None:
                result = {"status": "current", "version": current}
            else:
                version, assets = candidate
                ready = local.read_json(root / "update.json", {}).get("ready", {})
                if ready.get("version") == version and Path(ready.get("package", "")).is_dir():
                    local.verify_package(Path(ready["package"]))
                    result = {"status": "ready", "version": version}
                else:
                    filename = f"trellis-skills-{version}.zip"
                    checksum = reader(assets[filename + ".sha256"]["browser_download_url"], 4096).decode("ascii").strip()
                    match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?" + re.escape(filename), checksum)
                    if not match:
                        raise ValueError("Invalid release checksum file")
                    expected = match[1].lower()
                    digest = assets[filename].get("digest")
                    if digest and digest != "sha256:" + expected:
                        raise ValueError("GitHub asset digest and checksum disagree")
                    data = reader(assets[filename]["browser_download_url"], MAX_ZIP, deadline=time.monotonic() + 60)
                    if hashlib.sha256(data).hexdigest() != expected:
                        raise ValueError("Downloaded release failed SHA256 verification")
                    downloads = local.safe(root / "downloads")
                    downloads.mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory(prefix="unpack-", dir=downloads) as temporary:
                        unpack(data, version, Path(temporary))
                        package, _, _ = local.save_package(Path(temporary), root)
                    latest_installed = local.read_json(root / "installed.json", {}).get("version", current)
                    if local.version_tuple(version) > local.version_tuple(latest_installed):
                        def save_ready(state):
                            existing = state.get("ready", {})
                            if not existing or local.version_tuple(existing["version"]) <= local.version_tuple(version):
                                state["ready"] = {"version": version, "package": str(package), "sha256": expected}
                        state_change(profile, save_ready)
                    result = {"status": "ready", "version": version}
            state_change(profile, lambda state: state.update(check={**result, "finished_at": time.time()}))
            return result
        except Exception as exc:
            result = {"status": "failed", "message": str(exc)}
            state_change(profile, lambda state: state.update(check={**result, "finished_at": time.time()}))
            return result


def background_check(profile: Path, invocation: str, fixture=None):
    if (state_dir(profile) / "disabled").exists():
        return {"status": "disabled"}
    should_launch = False
    def mark(state):
        nonlocal should_launch
        invocations = state.get("invocations", [])
        if invocation not in invocations:
            should_launch = True
            state["invocations"] = [*invocations, invocation][-128:]
            if state.get("check", {}).get("status") not in ("checking", "queued"):
                state["check"] = {"status": "queued"}
    state_change(profile, mark)
    if not should_launch:
        return {"status": "already-checked-this-invocation"}
    # Run an immutable installed copy: a parallel installation may replace global files.
    package = local.read_json(state_dir(profile) / "installed.json", {}).get("package")
    script = Path(package) / "skills/trellis-setup/scripts/auto_update.py" if package else Path(__file__).resolve()
    args = [sys.executable, "-B", str(script), "worker", "--profile", str(profile)]
    if fixture:
        args += ["--release-fixture", str(fixture)]
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    child = subprocess.Popen(args, **kwargs)
    return {"status": "checking-in-background", "pid": child.pid}


def apply_pending(profile: Path, project: Path, wait_seconds=0):
    root = state_dir(profile)
    if (root / "disabled").exists():
        return {"status": "disabled"}
    deadline = time.monotonic() + min(15, max(0, wait_seconds))
    # A busy calling project is not a safe installation boundary.
    if local.busy(project):
        return {"status": "deferred", "reason": "current-project-busy"}
    while True:
        state = local.read_json(root / "update.json", {})
        if state.get("ready") or state.get("check", {}).get("status") not in ("checking", "queued") or time.monotonic() >= deadline:
            break
        time.sleep(0.1)
    installed = local.read_json(root / "installed.json", {})
    ready = state.get("ready", {})
    if ready and local.version_tuple(ready["version"]) > local.version_tuple(installed.get("version", "0.0.0")):
        source = Path(ready["package"])
    elif any(item.get("pending_version") for item in installed.get("projects", {}).values()):
        source = Path(installed["package"])
    else:
        return {"status": "current", "version": installed.get("version"), "check": state.get("check", {})}
    # Use the new package's installer, including its migration rules and state format.
    try:
        local.verify_package(source)
    except (OSError, ValueError) as exc:
        return {"status": "failed", "message": str(exc)}
    script = source / "skills/trellis-setup/scripts/auto_update.py"
    process = subprocess.run([sys.executable, "-B", str(script), "install", "--automatic", "--source", str(source), "--profile", str(profile)],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
    if process.returncode:
        return {"status": "failed", "message": process.stdout.strip() or process.stderr.strip()}
    return json.loads(process.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "worker", "status", "apply-pending", "install", "sync", "disable"))
    parser.add_argument("--profile", type=Path, default=local.migration.profile_dir())
    parser.add_argument("--project-root", type=Path, action="append", default=[])
    parser.add_argument("--invocation-id", default=None)
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--wait-seconds", type=float, default=0)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--registry-path", type=Path)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--include-active", action="store_true", help="Explicit initial migration only; automatic updates always defer busy projects")
    parser.add_argument("--automatic", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--release-fixture", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    profile = local.safe(args.profile)
    project = args.project_root[0].absolute() if args.project_root else Path.cwd()
    exit_code = 0
    try:
        if args.command == "disable":
            with local.lock(state_dir(profile) / "install.lock"):
                local.migration.atomic_write(state_dir(profile) / "disabled", b"disabled\n")
            result = {"status": "disabled"}
        elif args.command in ("install", "sync"):
            if args.source is None:
                parser.error("--source is required for installation")
            result = local.install(args.source, profile, global_install=args.command == "install",
                                   defer_active=not args.include_active, project_roots=args.project_root,
                                   registry_path=args.registry_path, backup_root=args.backup_root, automatic=args.automatic)
        elif args.command == "status":
            result = {"installed": local.read_json(state_dir(profile) / "installed.json", {}),
                      "update": local.read_json(state_dir(profile) / "update.json", {}),
                      "skills_source": local.project_source(profile, project)}
        elif args.command == "apply-pending":
            result = apply_pending(profile, project, args.wait_seconds)
        elif args.command == "check" and args.background:
            if args.release_fixture:
                fixture_fetch(profile, args.release_fixture)  # Validate before launching.
            result = background_check(profile, args.invocation_id or uuid.uuid4().hex, args.release_fixture)
        else:
            result = check_now(profile, fixture_fetch(profile, args.release_fixture) if args.release_fixture else fetch)
    except BlockingIOError:
        result = {"status": "another-operation-running"}
        exit_code = 1 if args.command in ("install", "sync", "disable") else 0
    except Exception as exc:
        result = {"status": "failed", "message": str(exc)}
        exit_code = 1 if args.command in ("install", "sync", "disable") else 0
    print(json.dumps(result, ensure_ascii=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
