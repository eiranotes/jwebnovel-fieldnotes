#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = Path.home() / "HermesWorkspace" / "project" / "fieldnotes-runtime"

# Files and trees needed for the private console and local acquisition/translation
# worker. The runtime mirror is intentionally not a Git repository.
RUNTIME_DIRS = (
    "config",
    "data",
    "docs",
    "scripts",
    "workers/novel-download",
    "workspace",
)
RUNTIME_FILES = (
    "index.html",
    "console.html",
    "console.js",
    "styles.css",
    "archive.js",
    ".nojekyll",
)

# State that can be mutated from the phone/private runtime and therefore must
# be imported before a canonical daily run or before refreshing the mirror.
MUTABLE_FILES = (
    "config/search-profiles.json",
    "config/automation.json",
    "data/full-translation-queue.json",
    "data/profile-rotation-state.json",
    "data/work-registry.json",
    "data/automation-logs.json",
)

PRIVATE_STATE_FILES = (
    "workspace/preference-feedback.json",
    "workspace/preference-model.json",
)

MUTABLE_WORKSPACE_DIRS = (
    "workspace/full-translations",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_is_newer(src: Path, dst: Path) -> bool:
    if not dst.exists():
        return True
    try:
        src_stat = src.stat()
        dst_stat = dst.stat()
        return src_stat.st_mtime_ns > dst_stat.st_mtime_ns or src_stat.st_size != dst_stat.st_size
    except OSError:
        return True


def copy_file(src_root: Path, dst_root: Path, rel: str) -> bool:
    src = src_root / rel
    if not src.exists() or not src.is_file():
        return False
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not source_is_newer(src, dst):
        return False
    shutil.copy2(src, dst)
    return True


def copy_tree(src_root: Path, dst_root: Path, rel: str) -> bool:
    src = src_root / rel
    if not src.exists() or not src.is_dir():
        return False
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)

    def copy_if_newer(src_name: str, dst_name: str) -> str:
        src_path = Path(src_name)
        dst_path = Path(dst_name)
        if source_is_newer(src_path, dst_path):
            shutil.copy2(src_path, dst_path)
        return str(dst_path)

    shutil.copytree(
        src,
        dst,
        dirs_exist_ok=True,
        copy_function=copy_if_newer,
        ignore=shutil.ignore_patterns(
            ".git",
            ".DS_Store",
            "__pycache__",
            "*.pyc",
            "private-console.pid",
            "private-console*.log",
        ),
    )
    return True


def ensure_runtime_marker() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    marker = {
        "schema_version": "1.0",
        "purpose": "private_non_git_runtime_mirror",
        "canonical_repo": str(ROOT),
        "runtime_root": str(RUNTIME),
        "updated_at": now(),
    }
    (RUNTIME / ".fieldnotes-runtime.json").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    git = RUNTIME / ".git"
    if git.exists():
        raise SystemExit(f"Refusing to use runtime mirror containing .git: {RUNTIME}")


def pull() -> dict:
    """Import newer phone/runtime mutable state into the canonical local repo."""
    if not RUNTIME.exists():
        return {"status": "runtime_missing", "runtime": str(RUNTIME), "files": 0, "trees": 0}
    files = 0
    trees = 0
    for rel in (*MUTABLE_FILES, *PRIVATE_STATE_FILES):
        files += int(copy_file(RUNTIME, ROOT, rel))
    for rel in MUTABLE_WORKSPACE_DIRS:
        trees += int(copy_tree(RUNTIME, ROOT, rel))
    return {"status": "pulled", "runtime": str(RUNTIME), "files": files, "trees": trees}


def push() -> dict:
    """Refresh the internal runtime mirror with newer canonical code/state."""
    ensure_runtime_marker()
    files = 0
    trees = 0
    for rel in RUNTIME_DIRS:
        trees += int(copy_tree(ROOT, RUNTIME, rel))
    for rel in RUNTIME_FILES:
        files += int(copy_file(ROOT, RUNTIME, rel))
    ensure_runtime_marker()
    return {"status": "pushed", "runtime": str(RUNTIME), "files": files, "trees": trees}


def install() -> dict:
    # Preserve any edits made from the phone before refreshing code/state.
    imported = pull() if RUNTIME.exists() else {"status": "first_install", "files": 0, "trees": 0}
    exported = push()
    return {"status": "installed", "pull": imported, "push": exported}


def status() -> dict:
    marker = RUNTIME / ".fieldnotes-runtime.json"
    return {
        "runtime": str(RUNTIME),
        "exists": RUNTIME.exists(),
        "is_git_repo": (RUNTIME / ".git").exists(),
        "marker": json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize the private internal Fieldnotes runtime mirror")
    parser.add_argument("command", choices=("install", "pull", "push", "status"))
    args = parser.parse_args()
    result = {"install": install, "pull": pull, "push": push, "status": status}[args.command]()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
