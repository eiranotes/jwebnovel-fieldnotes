"""Validation boundary shared by every translation model backend."""
from __future__ import annotations

import re
from pathlib import Path

from automation_store import AutomationError, digest, read_json


def validate_local_source_task(root: Path, work_id: str, payload: dict) -> tuple[Path, dict, str]:
    reference = payload.get("local_source_task")
    if not isinstance(reference, dict):
        raise AutomationError("LOCAL_SOURCE_REFERENCE_INVALID")
    raw_path = reference.get("path")
    expected_sha256 = reference.get("sha256")
    if (
        not isinstance(raw_path, str)
        or not Path(raw_path).is_absolute()
        or not isinstance(expected_sha256, str)
        or not re.fullmatch(r"[a-f0-9]{64}", expected_sha256)
    ):
        raise AutomationError("LOCAL_SOURCE_REFERENCE_INVALID")

    path = Path(raw_path).expanduser().resolve()
    workspace = (root / "workspace").resolve()
    chunk_id = payload.get("chunk_id")
    if (
        str(path) != raw_path
        or not path.is_relative_to(workspace)
        or path.parent.name != "tasks"
        or path.parent.parent.name != "translation"
        or not re.fullmatch(r"[0-9]{4,8}\.json", path.name)
        or chunk_id != path.stem
    ):
        raise AutomationError("LOCAL_SOURCE_REFERENCE_INVALID")
    if not path.is_file() or digest(path.read_bytes()) != expected_sha256:
        raise AutomationError("LOCAL_SOURCE_CHANGED")

    document = read_json(path)
    probe = document.get("local_source_probe") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("work_id") != work_id
        or document.get("chunk_id") != path.stem
        or not isinstance(probe, str)
        or not re.fullmatch(r"[a-f0-9]{32}", probe)
    ):
        raise AutomationError("LOCAL_SOURCE_REFERENCE_INVALID")
    return path, document, probe
