from __future__ import annotations

import hashlib
import logging
import os
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".pocketcode" / "cache" / "vm"

@dataclass
class LockfileEntry:
    ref: str
    resolved_url: str
    commit: str
    local_path: str

class StackVmLockfile:
    def __init__(self, path: Path):
        self.path = path
        self.entries: dict[str, LockfileEntry] = {}
        self.load()

    def load(self):
        if not self.path.is_file():
            return
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            for ref, item in data.get("dependencies", {}).items():
                self.entries[ref] = LockfileEntry(
                    ref=ref,
                    resolved_url=item.get("resolved_url", ""),
                    commit=item.get("commit", ""),
                    local_path=item.get("local_path", ""),
                )
        except Exception as e:
            logger.warning("Failed to load lockfile %s: %s", self.path, e)

    def save(self):
        data = {
            "dependencies": {
                ref: asdict(entry) for ref, entry in self.entries.items()
            }
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")

    def get_entry(self, ref: str) -> LockfileEntry | None:
        return self.entries.get(ref)

    def add_entry(self, entry: LockfileEntry):
        self.entries[entry.ref] = entry
        self.save()

def is_remote_ref(ref: str) -> bool:
    """Detects if a StackVM reference is remote."""
    return any(ref.startswith(p) for p in ("github:", "git+", "http://", "https://"))

def resolve_remote_ref(ref: str, workspace_root: Path) -> Path:
    """
    Resolves a remote reference to a local file path using a lockfile.
    """
    lockfile_path = workspace_root / "pocketcode.lock.yaml"
    lockfile = StackVmLockfile(lockfile_path)
    
    entry = lockfile.get_entry(ref)
    if entry:
        local_path = Path(entry.local_path)
        if local_path.is_file():
            return local_path

    # Not in lockfile or missing locally, resolve and fetch
    resolved_url, subpath = _parse_remote_ref(ref)
    commit = _get_remote_commit(resolved_url)
    
    # Cache key based on URL and commit
    cache_key = hashlib.sha256(f"{resolved_url}@{commit}".encode()).hexdigest()[:12]
    repo_cache_path = CACHE_DIR / cache_key
    
    if not repo_cache_path.exists():
        _clone_repo(resolved_url, commit, repo_cache_path)
    
    resolved_file = repo_cache_path / subpath
    if not resolved_file.is_file():
        # Try common suffixes if exact match fails
        for suffix in (".vm", ".md"):
            if (resolved_file.with_suffix(suffix)).is_file():
                resolved_file = resolved_file.with_suffix(suffix)
                break
        else:
            raise FileNotFoundError(f"Remote file '{subpath}' not found in {resolved_url} at {commit}")

    # Record in lockfile
    lockfile.add_entry(LockfileEntry(
        ref=ref,
        resolved_url=resolved_url,
        commit=commit,
        local_path=str(resolved_file.resolve())
    ))
    
    return resolved_file

def _parse_remote_ref(ref: str) -> tuple[str, str]:
    """Parses a remote ref into (git_url, subpath_within_repo)."""
    if ref.startswith("github:"):
        # Format github:user/repo/path/to/file
        parts = ref[7:].split("/", 2)
        if len(parts) < 2:
            raise ValueError(f"Invalid github reference: {ref}")
        user, repo = parts[0], parts[1]
        subpath = parts[2] if len(parts) > 2 else "index.vm"
        return f"https://github.com/{user}/{repo}.git", subpath
    
    if ref.startswith("git+"):
        # Format git+https://url.git/path/to/file
        url_part = ref[4:]
        if ".git/" in url_part:
            url, subpath = url_part.split(".git/", 1)
            return url + ".git", subpath
        return url_part, "index.vm"

    raise ValueError(f"Unsupported remote reference format: {ref}")

def _get_remote_commit(url: str) -> str:
    """Uses git ls-remote to find the latest commit hash (defaults to HEAD)."""
    try:
        output = subprocess.check_output(["git", "ls-remote", url, "HEAD"], text=True)
        return output.split()[0]
    except Exception as e:
        raise RuntimeError(f"Failed to resolve remote commit for {url}: {e}")

def _clone_repo(url: str, commit: str, dest: Path):
    """Clones a specific commit of a repository into a destination directory."""
    dest.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.check_call(["git", "init"], cwd=dest)
        subprocess.check_call(["git", "remote", "add", "origin", url], cwd=dest)
        subprocess.check_call(["git", "fetch", "--depth", "1", "origin", commit], cwd=dest)
        subprocess.check_call(["git", "checkout", "FETCH_HEAD"], cwd=dest)
    except Exception as e:
        if dest.exists():
            import shutil
            shutil.rmtree(dest)
        raise RuntimeError(f"Failed to clone repository {url} at {commit}: {e}")
