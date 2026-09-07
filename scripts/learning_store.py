#!/usr/bin/env python3
"""Private operational learning store for verified translation/discovery lessons.

This is deliberately not model training. It is a durable evidence ledger: new failure
signatures are recorded as observations, verified fixes are promoted to active lessons,
and later regressions lower confidence. Only compact, non-source metadata belongs here.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from automation_store import atomic_json, locked, now, read_json

ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "config" / "learning-policy.json"
ID_SAFE = re.compile(r"[^a-z0-9._-]+")
OUTCOMES = {"observed", "resolved", "regression", "confirmed"}


def policy(root: Path = ROOT) -> dict:
    return read_json(root / "config" / "learning-policy.json", {})


def store_path(root: Path = ROOT) -> Path:
    rel = str(policy(root).get("private_store") or "workspace/learning/operational-lessons.json")
    path = (root / rel).resolve()
    workspace = (root / "workspace").resolve()
    if path == workspace or not path.is_relative_to(workspace):
        raise ValueError("learning store must stay under workspace/")
    return path


def empty_store() -> dict:
    return {
        "schema_version": "1.0",
        "updated_at": None,
        "lessons": [],
    }


def load_store(root: Path = ROOT) -> dict:
    data = read_json(store_path(root), empty_store())
    if not isinstance(data, dict) or not isinstance(data.get("lessons"), list):
        return empty_store()
    return data


def _slug(value: str) -> str:
    cleaned = ID_SAFE.sub("-", value.lower()).strip("-.")[:72]
    return cleaned or "event"


def _default_id(domain: str, signature: str) -> str:
    import hashlib
    suffix = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:10]
    return f"{domain}.{_slug(signature)}.{suffix}"


def _find(data: dict, domain: str, signature: str, lesson_id: str | None = None) -> dict | None:
    for lesson in data.get("lessons", []):
        if lesson_id and lesson.get("lesson_id") == lesson_id:
            return lesson
        if lesson.get("domain") == domain and lesson.get("signature") == signature:
            return lesson
    return None


def _confidence(lesson: dict) -> float:
    evidence = lesson.get("evidence") or {}
    resolved = int(evidence.get("resolved", 0)) + int(evidence.get("confirmed", 0))
    regressions = int(evidence.get("regression", 0))
    observations = max(1, int(evidence.get("observed", 0)))
    if lesson.get("status") != "active":
        return min(0.49, round(resolved / (observations + regressions + 1), 3))
    return round(max(0.0, min(1.0, (resolved + 1) / (resolved + regressions + 1))), 3)


def seed_known(root: Path = ROOT) -> dict:
    cfg = policy(root)
    path = store_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    added = updated = 0
    with locked(path.with_suffix(path.suffix + ".lock")):
        data = load_store(root)
        for seed in cfg.get("seed_lessons", []):
            if not isinstance(seed, dict):
                continue
            domain = str(seed.get("domain") or "")
            signature = str(seed.get("signature") or "")
            if domain not in cfg.get("domains", []) or not signature:
                continue
            lesson = _find(data, domain, signature, str(seed.get("lesson_id") or "") or None)
            if lesson is None:
                lesson = {
                    "lesson_id": str(seed.get("lesson_id") or _default_id(domain, signature)),
                    "domain": domain,
                    "scope": str(seed.get("scope") or "general"),
                    "signature": signature,
                    "status": "active",
                    "resolution": str(seed.get("resolution") or ""),
                    "guard": str(seed.get("guard") or ""),
                    "confidence": float(seed.get("confidence", 1.0)),
                    "evidence": {"observed": 1, "resolved": 1, "regression": 0, "confirmed": 1},
                    "first_seen_at": now(),
                    "last_seen_at": now(),
                    "recent": [],
                }
                data["lessons"].append(lesson)
                added += 1
            else:
                lesson.update(
                    scope=str(seed.get("scope") or lesson.get("scope") or "general"),
                    status="active",
                    resolution=str(seed.get("resolution") or lesson.get("resolution") or ""),
                    guard=str(seed.get("guard") or lesson.get("guard") or ""),
                    confidence=max(float(lesson.get("confidence", 0)), float(seed.get("confidence", 1.0))),
                    last_seen_at=now(),
                )
                updated += 1
        data["lessons"].sort(key=lambda x: (str(x.get("domain")), str(x.get("lesson_id"))))
        data["updated_at"] = now()
        atomic_json(path, data)
    return {"status": "seeded", "added": added, "updated": updated, "path": str(path)}


def observe(
    domain: str,
    signature: str,
    outcome: str = "observed",
    *,
    scope: str = "general",
    resolution: str = "",
    guard: str = "",
    note: str = "",
    root: Path = ROOT,
) -> dict:
    cfg = policy(root)
    if domain not in cfg.get("domains", []):
        raise ValueError(f"unknown learning domain: {domain}")
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown learning outcome: {outcome}")
    signature = str(signature).strip()
    if not signature or len(signature) > 200:
        raise ValueError("signature must be 1..200 characters")
    note = str(note or "").strip()[:500]
    path = store_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path.with_suffix(path.suffix + ".lock")):
        data = load_store(root)
        lesson = _find(data, domain, signature)
        if lesson is None:
            lesson = {
                "lesson_id": _default_id(domain, signature),
                "domain": domain,
                "scope": scope or "general",
                "signature": signature,
                "status": "observed",
                "resolution": "",
                "guard": "",
                "confidence": 0.0,
                "evidence": {"observed": 0, "resolved": 0, "regression": 0, "confirmed": 0},
                "first_seen_at": now(),
                "last_seen_at": now(),
                "recent": [],
            }
            data["lessons"].append(lesson)
        evidence = lesson.setdefault("evidence", {"observed": 0, "resolved": 0, "regression": 0, "confirmed": 0})
        evidence[outcome] = int(evidence.get(outcome, 0)) + 1
        if outcome != "observed":
            evidence["observed"] = max(1, int(evidence.get("observed", 0)))
        if scope:
            lesson["scope"] = scope
        if resolution:
            lesson["resolution"] = resolution[:1200]
        if guard:
            lesson["guard"] = guard[:800]
        promotion = cfg.get("promotion") or {}
        resolved = int(evidence.get("resolved", 0)) + int(evidence.get("confirmed", 0))
        regressions = int(evidence.get("regression", 0))
        regression_rate = regressions / max(1, resolved + regressions)
        if lesson.get("resolution") and resolved >= int(promotion.get("min_resolved_successes", 1)) and regression_rate <= float(promotion.get("max_regression_rate", 0.25)):
            lesson["status"] = "active"
        elif outcome == "regression" and regression_rate > float(promotion.get("max_regression_rate", 0.25)):
            lesson["status"] = "observed"
        lesson["last_seen_at"] = now()
        lesson["last_outcome"] = outcome
        lesson["confidence"] = _confidence(lesson)
        recent = lesson.setdefault("recent", [])
        recent.append({"at": now(), "outcome": outcome, "note": note})
        del recent[:-20]
        data["updated_at"] = now()
        data["lessons"].sort(key=lambda x: (str(x.get("domain")), str(x.get("lesson_id"))))
        atomic_json(path, data)
    return lesson


def safe_observe(*args, **kwargs) -> dict | None:
    """Best-effort learning hook; never turns a production operation into a failure."""
    try:
        root = kwargs.get("root", ROOT)
        if not (Path(root) / "config" / "learning-policy.json").exists():
            return None
        return observe(*args, **kwargs)
    except Exception:
        return None


def active_context(domain: str, *, root: Path = ROOT, scope: str | None = None) -> dict:
    cfg = policy(root)
    limit = int((cfg.get("promotion") or {}).get("active_context_limit", 24))
    lessons = []
    for lesson in load_store(root).get("lessons", []):
        if lesson.get("domain") != domain or lesson.get("status") != "active":
            continue
        if scope and lesson.get("scope") != scope:
            continue
        lessons.append({
            "lesson_id": lesson.get("lesson_id"),
            "scope": lesson.get("scope"),
            "signature": lesson.get("signature"),
            "resolution": lesson.get("resolution"),
            "guard": lesson.get("guard"),
            "confidence": lesson.get("confidence"),
        })
    lessons.sort(key=lambda x: (-float(x.get("confidence") or 0), str(x.get("lesson_id"))))
    return {"domain": domain, "lessons": lessons[:limit], "count": min(len(lessons), limit)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    rec = sub.add_parser("record")
    rec.add_argument("--domain", required=True, choices=("translation", "discovery"))
    rec.add_argument("--signature", required=True)
    rec.add_argument("--outcome", choices=sorted(OUTCOMES), default="observed")
    rec.add_argument("--scope", default="general")
    rec.add_argument("--resolution", default="")
    rec.add_argument("--guard", default="")
    rec.add_argument("--note", default="")
    ctx = sub.add_parser("context")
    ctx.add_argument("--domain", required=True, choices=("translation", "discovery"))
    ctx.add_argument("--scope")
    sub.add_parser("status")
    args = p.parse_args()
    if args.cmd == "seed":
        result = seed_known()
    elif args.cmd == "record":
        result = observe(args.domain, args.signature, args.outcome, scope=args.scope, resolution=args.resolution, guard=args.guard, note=args.note)
    elif args.cmd == "context":
        result = active_context(args.domain, scope=args.scope)
    else:
        data = load_store()
        result = {
            "path": str(store_path()),
            "updated_at": data.get("updated_at"),
            "lessons": len(data.get("lessons", [])),
            "active": sum(x.get("status") == "active" for x in data.get("lessons", [])),
            "translation": sum(x.get("domain") == "translation" for x in data.get("lessons", [])),
            "discovery": sum(x.get("domain") == "discovery" for x in data.get("lessons", [])),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
