#!/usr/bin/env python3
"""Build immutable, per-work Project Sources; proof values never enter model tasks."""
from __future__ import annotations

import argparse
import json
import re
import secrets
from pathlib import Path

from automation_store import AutomationError, atomic_bytes, atomic_json, digest, locked, now, read_json, within

ROOT = Path(__file__).resolve().parent.parent
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}\Z")
GUIDES = ("translation-guide.md", "character-guide.md", "style-guide.md")
MAX_GUIDE_BYTES = 96_000


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
            text += f"## Canonical work data\n\n```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```\n\n"
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


def build_work(work_dir: Path, root: Path = ROOT) -> dict:
    work_dir = within(root / "workspace", work_dir)
    metadata = read_json(work_dir / "metadata.json")
    work_id = str(metadata.get("work_id", ""))
    if not ID.fullmatch(work_id):
        raise AutomationError("INVALID_WORK_ID")
    glossary = read_json(work_dir / "glossary.json", {})
    payload = {"work_id": work_id, "title": metadata.get("title"), "author": metadata.get("author"),
               "platform": metadata.get("platform"), "url": metadata.get("url"), "glossary": glossary}
    notes = []
    for name in GUIDES:
        guide = work_dir / name
        if guide.exists():
            notes.append(f"## {name}\n\n{_text(guide)}")
    if not notes:
        notes.append("## Work-specific guides\n\nNo separate character or voice guide has been approved yet. Do not invent one. Use the explicit glossary/ruby above and the current source; record new decisions for review.\n")
    # Common application rules participate in the revision hash so edits cannot be hidden
    # behind an unchanged source version. No original chapter text is copied into this pack.
    instructions = _text(root / "templates/project-context/PROJECT_INSTRUCTIONS.md")
    return _artifact(root, f"WORK_{work_id}", payload, "\n\n".join(notes) + "\n\n## Common instruction revision\n" + digest(instructions.encode()) + "\n")


def build_common(root: Path = ROOT) -> dict:
    rules = _text(root / "templates/project-context/PROJECT_INSTRUCTIONS.md")
    context = _text(root / "templates/project-context/GLOBAL_CONTEXT.md")
    return _artifact(root, "GLOBAL_CONTEXT", {}, rules + "\n\n" + context)


def public_pack(pack: dict) -> dict:
    """Task-safe descriptor. Neither a token echo nor a prompt-supplied probe proves retrieval."""
    return {k: pack[k] for k in ("source_name", "filename", "context_version", "content_hash", "file_sha256")}


def source_probe_task(work_id: str, common: dict, work: dict) -> dict:
    return {"kind": "project_source_probe", "work_id": work_id,
            "sources": [public_pack(common), public_pack(work)],
            "instructions": "Retrieve both exact named Project Sources. Return their source_probe values from the file contents, without guessing. Do not read local files or call Steroids. If unavailable return {status:source_unavailable}.",
            "output_contract": {"status": "ready or source_unavailable", "work_id": work_id,
                                "sources": [{"filename": "exact filename", "source_probe": "value read from that file"}]}}


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
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()
    work_dir = Path(args.work_dir).expanduser()
    work_dir = work_dir if work_dir.is_absolute() else ROOT / work_dir
    work, common = build_work(work_dir), build_common()
    print(json.dumps({"common": public_pack(common), "work": public_pack(work),
                      "source_files": [common["path"], work["path"]], "status": "sync_required"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
