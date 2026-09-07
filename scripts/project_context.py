#!/usr/bin/env python3
"""Build the immutable common Project Sources used by every Fieldnotes work chat."""
from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from automation_store import AutomationError, atomic_bytes, atomic_json, digest, locked, now, read_json

ROOT = Path(__file__).resolve().parent.parent
MAX_GUIDE_BYTES = 96_000
COMMON_SOURCES = (
    ("GLOBAL_CONTEXT", "GLOBAL_CONTEXT.md"),
    # The live Steroids project-source schema already permits WORK_<slug>. These two names
    # are application-wide sources, not per-novel WORK packs; keeping the accepted prefix lets
    # us deploy this cleanup without restarting or replacing the currently healthy app bundle.
    ("WORK_translation_rules", "TRANSLATION_RULES.md"),
    ("WORK_user_instructions", "USER_INSTRUCTIONS.md"),
)


def _text(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > MAX_GUIDE_BYTES:
        raise AutomationError("CONTEXT_GUIDE_TOO_LARGE", path.name)
    return data.decode("utf-8")


def _artifact(root: Path, name: str, data: dict, body: str) -> dict:
    directory = root / "workspace" / "project-context" / name
    with locked(directory / ".build.lock"):
        previous = read_json(directory / "current.json", {})
        content_hash = digest({"data": data, "body": body})
        if previous.get("content_hash") == content_hash:
            file = directory / previous["filename"]
            if not file.exists() or digest(file.read_bytes()) != previous.get("file_sha256"):
                raise AutomationError("CONTEXT_CACHE_TAMPERED", name)
            return previous
        revision = int(previous.get("context_version", 0)) + 1
        probe = secrets.token_hex(16)
        filename = f"{name}_v{revision:04d}_{content_hash[:12]}.md"
        header = {"source_name": name, "context_version": revision,
                  "content_hash": content_hash, "generated_at": now(), "source_probe": probe}
        text = f"# {name}\n\n## Revision and retrieval proof\n\n```json\n{json.dumps(header, ensure_ascii=False, indent=2)}\n```\n\n"
        if data:
            text += f"## Canonical context data\n\n```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```\n\n"
        text += body
        encoded = text.encode("utf-8")
        if len(encoded) > 240_000:
            raise AutomationError("CONTEXT_PACK_TOO_LARGE", name)
        path = directory / filename
        if path.exists():
            raise AutomationError("CONTEXT_REVISION_COLLISION", filename)
        atomic_bytes(path, encoded)
        result = {**header, "filename": filename, "file_sha256": digest(encoded),
                  "path": str(path.relative_to(root)), "upload_state": "sync_required"}
        atomic_json(directory / "current.json", result)
        return result


def build_common(root: Path = ROOT) -> dict:
    """Backward-compatible accessor for the workflow/context anchor."""
    return build_common_packs(root)[0]


def build_common_packs(root: Path = ROOT) -> list[dict]:
    """Return the three Project-wide sources; no work-specific source is created here."""
    return [_artifact(root, source_name, {}, _text(root / "templates/project-context" / template))
            for source_name, template in COMMON_SOURCES]


def public_pack(pack: dict) -> dict:
    """Task-safe descriptor. Neither a token echo nor a prompt-supplied probe proves retrieval."""
    return {k: pack[k] for k in ("source_name", "filename", "context_version", "content_hash", "file_sha256")}


def source_probe_task(work_id: str, *packs: dict, conversation_title: str | None = None) -> dict:
    if not packs:
        raise AutomationError("PROJECT_SOURCE_PROOF_MISMATCH")
    task = {"kind": "project_source_probe", "work_id": work_id,
            "sources": [public_pack(pack) for pack in packs],
            "instructions": "Retrieve every exact named Project Source in sources. Return its source_probe value from the file contents, without guessing. Do not read local files or call Steroids. If unavailable return {status:source_unavailable}.",
            "output_contract": {"status": "ready or source_unavailable", "work_id": work_id,
                                "sources": [{"filename": "exact filename", "source_probe": "value read from that file"}]}}
    if conversation_title:
        task["conversation_title"] = conversation_title
    return task


def verify_source_probe(answer: dict, work_id: str, packs: list[dict]) -> dict:
    if not isinstance(answer, dict) or answer.get("status") != "ready" or answer.get("work_id") != work_id:
        raise AutomationError("PROJECT_SOURCE_UNAVAILABLE")
    rows = answer.get("sources")
    if not isinstance(rows, list) or len(rows) != len(packs):
        raise AutomationError("PROJECT_SOURCE_PROOF_MISMATCH")
    wanted = {p["filename"]: p["source_probe"] for p in packs}
    got = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("filename"), str) or not isinstance(row.get("source_probe"), str) or row.get("filename") in got:
            raise AutomationError("PROJECT_SOURCE_PROOF_MISMATCH")
        got[row.get("filename")] = row.get("source_probe")
    if got != wanted:
        raise AutomationError("PROJECT_SOURCE_PROOF_MISMATCH")
    return {"verified_at": now(), "work_id": work_id, "sources": [public_pack(p) for p in packs]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    packs = build_common_packs()
    print(json.dumps({"sources": [public_pack(pack) for pack in packs],
                      "source_files": [pack["path"] for pack in packs],
                      "status": "sync_required"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
