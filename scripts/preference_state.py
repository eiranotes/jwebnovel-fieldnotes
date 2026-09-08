"""Shared process lock and crash-safe JSON writes for private preference evidence."""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

# Bump only when ranking/feature semantics become incomparable, with a migration decision.
# Full source hashes remain provenance and rebuild-cache invalidation, not evaluation cohorts.
SCORING_COHORT_ID = 'bounded-additive-v2.1'
_local = threading.local()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def load(path: Path, fallback):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else fallback


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


@contextmanager
def state_lock(workspace: Path):
    path = (workspace / '.preference.lock').resolve()
    held = getattr(_local, 'held', set())
    if path in held:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        _local.held = held | {path}
        try:
            yield
        finally:
            _local.held = held
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def code_revision() -> str:
    root = Path(__file__).parent
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(root.glob('preference*.py'))})
