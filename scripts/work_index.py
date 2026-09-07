#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rebuild_work_index import OUT, canonical, rebuild
from learning_store import safe_observe


def load_index() -> dict:
    if not OUT.exists():
        rebuild()
    return json.loads(OUT.read_text(encoding="utf-8"))


def annotate(items: list[dict]) -> list[dict]:
    index = load_index()
    by_key = {x["canonical_key"]: x for x in index.get("works", [])}
    by_url = {}
    for row in index.get("works", []):
        if row.get("url"):
            by_url[row["url"]] = row
        for inst in row.get("platform_instances", []):
            if inst.get("url"):
                by_url[inst["url"]] = row
    output = []
    for item in items:
        key = canonical(item)
        seen = by_key.get(key) or by_url.get(item.get("url"))
        output.append({**item, "canonical_key": key, "seen": bool(seen), "seen_record": seen})
    return output


def main() -> int:
    p = argparse.ArgumentParser(description="Check discovery candidates against the persistent work index")
    p.add_argument("--input", help="JSON file containing a candidate object or array; omit to read stdin")
    p.add_argument("--unseen-only", action="store_true")
    args = p.parse_args()
    raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
    data = json.loads(raw)
    items = data if isinstance(data, list) else [data]
    rows = annotate(items)
    seen_count = sum(bool(x.get("seen")) for x in rows)
    if seen_count:
        safe_observe(
            "discovery", "repeat_or_crosspost_candidate", "confirmed",
            scope="candidate_pool", note=f"seen candidates filtered={seen_count}",
            root=Path(__file__).resolve().parent.parent,
        )
    if args.unseen_only:
        rows = [x for x in rows if not x["seen"]]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
