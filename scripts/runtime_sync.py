#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from contextlib import ExitStack
from preference_state import state_lock, save
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
    "taste.html",
    "taste.js",
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
    "workspace/daily-taste-state.json",
    "workspace/preference-learning-history.json",
    "workspace/preference-ranking-traces.json",
)

MUTABLE_WORKSPACE_DIRS = (
    "workspace/full-translations",
    "workspace/learning",
    "workspace/preference-evidence",
    "workspace/preference-revisions",
)


IMMUTABLE_TREES = ('workspace/preference-revisions','workspace/preference-evidence')


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


def copy_file(src_root: Path, dst_root: Path, rel: str, *, force: bool = False) -> bool:
    src = src_root / rel
    if not src.exists():
        dst = dst_root / rel
        if force and dst.is_file():
            dst.unlink(); return True
        return False
    if not src.is_file():
        return False
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not force and not source_is_newer(src, dst):
        return False
    shutil.copy2(src, dst)
    return True


def copy_tree(src_root: Path, dst_root: Path, rel: str, *, force: bool = False) -> bool:
    src = src_root / rel
    if not src.exists() or not src.is_dir():
        return False
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)

    def copy_if_newer(src_name: str, dst_name: str) -> str:
        src_path = Path(src_name)
        dst_path = Path(dst_name)
        immutable=any(str(src_path.relative_to(src_root)).startswith(rel+'/') for rel in IMMUTABLE_TREES)
        if immutable and dst_path.is_file() and entry_hash(src_path)==entry_hash(dst_path):return str(dst_path)
        if force or source_is_newer(src_path, dst_path):
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
            ".preference.lock",
            "*.tmp",
            "private-console.pid",
            "private-console*.log",
        ),
    )
    return True


def _ignored_runtime_path(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in {".git", "__pycache__"} for part in rel.parts):
        return True
    name = path.name
    return (
        name == ".DS_Store"
        or name == ".preference.lock"
        or name.endswith(".tmp")
        or name.endswith(".pyc")
        or name == "private-console.pid"
        or (name.startswith("private-console") and name.endswith(".log"))
    )


def entry_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if not path.is_dir():
        return None
    digest = hashlib.sha256()
    for child in sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: str(p.relative_to(path))):
        if _ignored_runtime_path(child, path):
            continue
        rel = str(child.relative_to(path)).replace("\\", "/")
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(child.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def entry_mtime(path: Path) -> int:
    if not path.exists():
        return -1
    if path.is_file():
        return path.stat().st_mtime_ns
    mtimes = [path.stat().st_mtime_ns]
    mtimes.extend(p.stat().st_mtime_ns for p in path.rglob("*") if p.is_file() and not _ignored_runtime_path(p, path))
    return max(mtimes)


def mutable_entries() -> tuple[tuple[str, str], ...]:
    return tuple((rel, "file") for rel in (*MUTABLE_FILES, *PRIVATE_STATE_FILES)) + tuple(
        (rel, "tree") for rel in MUTABLE_WORKSPACE_DIRS
    )


def runtime_marker() -> dict:
    path = RUNTIME / ".fieldnotes-runtime.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def ensure_runtime_marker(mutable_hashes: dict | None = None) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    previous = runtime_marker()
    marker = {
        "schema_version": "1.1",
        "purpose": "private_non_git_runtime_mirror",
        "canonical_repo": str(ROOT),
        "runtime_root": str(RUNTIME),
        "updated_at": now(),
        "mutable_hashes": dict(previous.get("mutable_hashes") or {}) if mutable_hashes is None else mutable_hashes,
    }
    (RUNTIME / ".fieldnotes-runtime.json").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    git = RUNTIME / ".git"
    if git.exists():
        raise SystemExit(f"Refusing to use runtime mirror containing .git: {RUNTIME}")


def _set_marker_hashes(updates: dict[str, str | None]) -> None:
    marker = runtime_marker()
    hashes = dict(marker.get("mutable_hashes") or {})
    hashes.update(updates)
    ensure_runtime_marker(hashes)


def _pull() -> dict:
    """Import runtime-only mutable changes; refuse silent two-sided overwrites."""
    if not RUNTIME.exists():
        return {"status": "runtime_missing", "runtime": str(RUNTIME), "files": 0, "trees": 0}
    marker = runtime_marker()
    previous = dict(marker.get("mutable_hashes") or {})
    imports: list[tuple[str, str]] = []
    conflicts: list[dict] = []
    baseline_updates: dict[str, str | None] = {}
    unions=[]
    for rel, kind in mutable_entries():
        canonical = ROOT / rel
        runtime = RUNTIME / rel
        canonical_hash = entry_hash(canonical)
        runtime_hash = entry_hash(runtime)
        if rel in IMMUTABLE_TREES:
            left={str(p.relative_to(canonical)):p for p in canonical.rglob('*') if p.is_file() and not _ignored_runtime_path(p,canonical)} if canonical.exists() else {}
            right={str(p.relative_to(runtime)):p for p in runtime.rglob('*') if p.is_file() and not _ignored_runtime_path(p,runtime)} if runtime.exists() else {}
            for leaf in sorted(set(left)|set(right)):
                if leaf in left and leaf in right:
                    if entry_hash(left[leaf])!=entry_hash(right[leaf]):
                        conflicts.append({'path':rel+'/'+leaf,'canonical_sha256':entry_hash(left[leaf]),'runtime_sha256':entry_hash(right[leaf]),'reason':'immutable_content_collision'})
                elif leaf in left:unions.append((ROOT,RUNTIME,rel+'/'+leaf))
                else:unions.append((RUNTIME,ROOT,rel+'/'+leaf))
            continue
        if rel not in previous:
            # Upgrade path from the old mtime-only mirror. If both copies differ, preserve the
            # more recently written side once, then establish a content-hash baseline.
            if runtime_hash is not None and runtime_hash != canonical_hash and entry_mtime(runtime) > entry_mtime(canonical):
                imports.append((rel, kind))
                baseline_updates[rel] = runtime_hash
            elif runtime_hash == canonical_hash:
                baseline_updates[rel] = canonical_hash
            continue
        last_hash = previous.get(rel)
        runtime_changed = runtime_hash != last_hash
        canonical_changed = canonical_hash != last_hash
        if runtime_changed and canonical_changed and runtime_hash != canonical_hash:
            conflicts.append({"path": rel, "canonical_sha256": canonical_hash, "runtime_sha256": runtime_hash, "last_synced_sha256": last_hash})
        elif runtime_changed and not canonical_changed:
            imports.append((rel, kind))
            baseline_updates[rel] = runtime_hash
        elif runtime_hash == canonical_hash:
            baseline_updates[rel] = canonical_hash
    if conflicts:
        return {"status": "conflict", "runtime": str(RUNTIME), "files": 0, "trees": 0, "conflicts": conflicts}
    files = 0
    trees = 0
    for rel, kind in imports:
        if kind == "file":
            files += int(copy_file(RUNTIME, ROOT, rel, force=True))
        else:
            trees += int(copy_tree(RUNTIME, ROOT, rel, force=True))
    for src,dst,rel in unions:copy_file(src,dst,rel,force=True)
    for rel in IMMUTABLE_TREES:
        if (ROOT/rel).exists() or (RUNTIME/rel).exists():baseline_updates[rel]=entry_hash(ROOT/rel)
    if baseline_updates:
        _set_marker_hashes(baseline_updates)
    return {"status": "pulled", "runtime": str(RUNTIME), "files": files, "trees": trees, "immutable_files_merged":len(unions), "conflicts": []}


def _push(*, preserve_runtime: bool = True) -> dict:
    """Refresh the mirror after hash-based reconciliation of private mutable state."""
    preserved = pull() if preserve_runtime and RUNTIME.exists() else None
    if preserved and preserved.get("status") == "conflict":
        return {"status": "conflict", "runtime": str(RUNTIME), "preserved_runtime": preserved, "files": 0, "trees": 0}
    ensure_runtime_marker()
    files = 0
    trees = 0
    for rel in RUNTIME_DIRS:
        trees += int(copy_tree(ROOT, RUNTIME, rel, force=True))
    for rel in RUNTIME_FILES:
        files += int(copy_file(ROOT, RUNTIME, rel, force=True))
    hashes = {rel: entry_hash(ROOT / rel) for rel, _ in mutable_entries()}
    ensure_runtime_marker(hashes)
    return {"status": "pushed", "runtime": str(RUNTIME), "preserved_runtime": preserved, "files": files, "trees": trees}


def _install() -> dict:
    # Preserve any edits made from the phone before refreshing code/state.
    imported = pull() if RUNTIME.exists() else {"status": "first_install", "files": 0, "trees": 0}
    if imported.get("status") == "conflict":
        return {"status": "conflict", "pull": imported, "push": None}
    exported = push(preserve_runtime=False)
    return {"status": "installed", "pull": imported, "push": exported}


def _synchronized(fn, **kwargs):
    with ExitStack() as stack:
        for root in sorted({ROOT.resolve(), RUNTIME.resolve()}, key=str):
            stack.enter_context(state_lock(root / 'workspace'))
        return fn(**kwargs)


def pull() -> dict:
    if not RUNTIME.exists():
        return {"status":"runtime_missing","runtime":str(RUNTIME),"files":0,"trees":0}
    return _synchronized(_pull)


def push(*, preserve_runtime: bool = True) -> dict:
    return _synchronized(_push, preserve_runtime=preserve_runtime)


def install() -> dict:
    return _synchronized(_install)


def resolve(path: str, prefer: str, expected_canonical: str | None, expected_runtime: str | None) -> dict:
    """Explicit CAS resolution of one conflict; preserve both old versions before mutation."""
    with ExitStack() as stack:
        for root in sorted({ROOT.resolve(),RUNTIME.resolve()},key=str):stack.enter_context(state_lock(root/'workspace'))
        rel=Path(path)
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe conflict path')
        mutable={r for r,_ in mutable_entries()}
        leaf=any(path.startswith(tree+'/') for tree in IMMUTABLE_TREES)
        if path not in mutable and not leaf:raise ValueError('path is not reconciled state')
        if path in IMMUTABLE_TREES:raise ValueError('resolve an exact immutable collision file, never discard a whole archive tree')
        left,right=ROOT/path,RUNTIME/path
        hashes=(entry_hash(left),entry_hash(right))
        if hashes!=(expected_canonical,expected_runtime):raise ValueError('state changed since conflict inspection; inspect again')
        if prefer not in ('canonical','runtime'):raise ValueError('prefer canonical or runtime')
        receipt=ROOT/'.tmp/runtime-sync-conflicts'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
        for side,source in [('canonical',left),('runtime',right)]:
            dest=receipt/side/path;dest.parent.mkdir(parents=True,exist_ok=True)
            if source.is_dir():shutil.copytree(source,dest)
            elif source.exists():shutil.copy2(source,dest)
        save(receipt/'receipt.json',{'path':path,'prefer':prefer,'canonical_hash':hashes[0],'runtime_hash':hashes[1]})
        src_root,dst_root=(ROOT,RUNTIME) if prefer=='canonical' else (RUNTIME,ROOT)
        if not (src_root/path).exists() and (dst_root/path).is_dir():
            shutil.rmtree(dst_root/path)
        elif (src_root/path).is_dir():
            if (dst_root/path).exists():shutil.rmtree(dst_root/path)
            copy_tree(src_root,dst_root,path,force=True)
        else:copy_file(src_root,dst_root,path,force=True)
        baseline=next((tree for tree in IMMUTABLE_TREES if path.startswith(tree+'/')),path)
        if entry_hash(ROOT/baseline)==entry_hash(RUNTIME/baseline):_set_marker_hashes({baseline:entry_hash(ROOT/baseline)})
        return {'status':'resolved','path':path,'prefer':prefer,'backup':str(receipt)}


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
    parser.add_argument("command", choices=("install", "pull", "push", "status", "resolve"))
    parser.add_argument('--path');parser.add_argument('--prefer',choices=('canonical','runtime'))
    parser.add_argument('--expected-canonical');parser.add_argument('--expected-runtime')
    args = parser.parse_args()
    if args.command=='resolve':
        if not all((args.path,args.prefer,args.expected_canonical,args.expected_runtime)):parser.error('resolve requires path, prefer and both inspected hashes')
        result=resolve(args.path,args.prefer,None if args.expected_canonical=='missing' else args.expected_canonical,None if args.expected_runtime=='missing' else args.expected_runtime)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    result = {"install": install, "pull": pull, "push": push, "status": status}[args.command]()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status")=="conflict" else 0


if __name__ == "__main__":
    raise SystemExit(main())
