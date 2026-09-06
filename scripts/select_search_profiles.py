#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from automation_log import log_event, new_run_id


ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "search-profiles.json"
STATE = ROOT / "data" / "profile-rotation-state.json"


def load(path: Path, fallback: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def choose(config: dict, state: dict, date_key: str) -> tuple[list[dict], str]:
    enabled = [p for p in config.get("profiles", []) if p.get("enabled")]
    selected_ids = list(config.get("selection", {}).get("selected_profile_ids") or [])
    selected = [p for p in enabled if p.get("profile_id") in selected_ids]
    if selected:
        return selected, "explicit_selected"
    if not enabled:
        return [], "none_enabled"

    sel = config.get("selection", {})
    mode = sel.get("when_none", "round_robin")
    batch = max(1, min(int(sel.get("rotation_batch_size", 1) or 1), len(enabled)))
    if mode == "all_enabled":
        return enabled, mode
    if mode == "least_recently_run":
        meta = state.get("profiles", {})
        ordered = sorted(enabled, key=lambda p: (meta.get(p.get("profile_id"), {}).get("last_selected_at") or "", p.get("profile_id") or ""))
        return ordered[:batch], mode
    if mode == "random_daily":
        digest = hashlib.sha256(date_key.encode("utf-8")).digest()
        start = int.from_bytes(digest[:4], "big") % len(enabled)
        rotated = enabled[start:] + enabled[:start]
        return rotated[:batch], mode

    cursor = int(state.get("round_robin_cursor", 0) or 0) % len(enabled)
    rotated = enabled[cursor:] + enabled[:cursor]
    return rotated[:batch], "round_robin"


def commit_state(state: dict, chosen: list[dict], mode: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    meta = state.setdefault("profiles", {})
    for profile in chosen:
        pid = profile.get("profile_id")
        row = meta.setdefault(pid, {})
        row["last_selected_at"] = stamp
        row["selected_count"] = int(row.get("selected_count", 0)) + 1
    if mode == "round_robin" and chosen:
        state["round_robin_cursor"] = int(state.get("round_robin_cursor", 0)) + len(chosen)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def consume_explicit_selection(config: dict, mode: str) -> None:
    selection = config.setdefault("selection", {})
    if mode != "explicit_selected" or selection.get("explicit_selection_mode", "once") != "once":
        return
    selection["selected_profile_ids"] = []
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    p.add_argument("--commit", action="store_true")
    args = p.parse_args()
    config = load(CONFIG, {})
    state = load(STATE, {"schema_version": "1.0", "round_robin_cursor": 0, "profiles": {}})
    chosen, mode = choose(config, state, args.date)
    if args.commit:
        commit_state(state, chosen, mode)
        consume_explicit_selection(config, mode)
        run_id = new_run_id("profile-select")
        log_event(
            task="profile_selection",
            action="select",
            status="done",
            run_id=run_id,
            message=f"{len(chosen)} search profile(s) selected",
            details={"mode": mode, "profile_ids": [x.get("profile_id") for x in chosen]},
            public_details={"mode": mode, "count": len(chosen)},
        )
    print(json.dumps({"mode": mode, "profiles": chosen}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
