#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "data" / "research-index.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scaffold a dated research entry.")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--title", default="Untitled research entry")
    parser.add_argument("--continuation-of", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        dt.date.fromisoformat(args.date)
    except ValueError as exc:
        raise SystemExit("Invalid --date. Use YYYY-MM-DD.") from exc

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    same_day = [entry for entry in index if entry.get("date") == args.date]
    sequence = max([int(entry.get("sequence", 0)) for entry in same_day] + [0]) + 1
    entry_id = f"{args.date}-{sequence:02d}"

    json_path = ROOT / "data" / "entries" / f"{entry_id}.json"
    md_path = ROOT / "docs" / "entries" / f"{entry_id}.md"
    html_path = ROOT / "entries" / f"{entry_id}.html"

    for target in (json_path, md_path, html_path):
        if target.exists():
            raise SystemExit(f"Refusing to overwrite: {target.relative_to(ROOT)}")

    print(entry_id)
    if args.dry_run:
        return 0

    data = {
        "schema_version": "1.2",
        "entry_id": entry_id,
        "date": args.date,
        "sequence": sequence,
        "continuation_of": args.continuation_of,
        "title": args.title,
        "method_version_used": "0.4",
        "current_protocol_version": "0.4",
        "request_snapshot": "",
        "reference_works": [],
        "anti_reference_works": [],
        "hard_filters": {
            "platforms": [],
            "genres": [],
            "min_chars": None,
            "must": [],
            "must_not": [],
            "publication": None,
        },
        "length_policy": {
            "source": "global_default",
            "default_min_chars": 300000,
            "explicit_min_chars": None,
            "effective_min_chars": 300000,
            "allow_high_fit_exception": True,
            "exception_label": "LENGTH EXCEPTION",
        },
        "soft_preferences": [],
        "allowed_exceptions": [],
        "style_dimensions": [],
        "sampling_plan": {
            "s0_for_all_survivors": True,
            "deeper_samples": ["S1", "S2"],
            "adaptive_s3": True,
        },
        "learning_lessons_applied": [],
        "discovery_incidents_observed": [],
        "results": {
            "shortlist": [],
            "queue": [],
            "deprioritized": [],
            "excluded": [],
        },
        "checked_at": args.date,
    }

    markdown = f"""# {entry_id} — {args.title}

## Request snapshot

TBD

## Reference / anti-reference

TBD

## Active filters

### DEFAULT LENGTH

- 300,000자 이상
- 분량 외 핵심 조건이 매우 강하게 일치하면 LENGTH EXCEPTION 허용

### MUST

- TBD

### MUST NOT

- TBD

### PREFER

- TBD

### TOLERATE

- TBD

## Request-specific style fingerprint

TBD

## Harvest log

TBD

## Applied learning lessons / new incidents

TBD

## Shortlist

TBD

## Queue / rejected

TBD

## Search yield

TBD
"""

    safe_title = html.escape(args.title)
    page = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{entry_id} — {safe_title}</title>
  <link rel="stylesheet" href="../styles.css">
</head>
<body class="entry-page">
  <aside class="rail">ENTRY · {args.date.replace('-', '.')} · {sequence:02d}</aside>
  <main>
    <nav class="wrap entry-nav"><a href="../index.html">← Archive</a><a href="../docs/entries/{entry_id}.md">Markdown</a></nav>
    <header class="hero wrap">
      <p class="kicker">RESEARCH ENTRY · DRAFT</p>
      <div class="hero-grid"><div><h1>{safe_title}</h1><p class="deck">Request snapshot and findings will be written here.</p></div><p class="side-note"><b>{entry_id}</b><br>Default length: 300,000 chars. High-fit underlength works may be kept as LENGTH EXCEPTION.</p></div>
    </header>
  </main>
</body>
</html>
"""

    index_entry = {
        "entry_id": entry_id,
        "date": args.date,
        "sequence": sequence,
        "title": args.title,
        "summary": "Research entry scaffold — pending findings.",
        "reference_works": [],
        "criteria_terms": [],
        "platforms": [],
        "genres": [],
        "min_chars": 300000,
        "length_policy": "default_with_high_fit_exception",
        "status": "draft",
        "candidate_count": 0,
        "shortlist_count": 0,
        "page": f"entries/{entry_id}.html",
        "doc": f"docs/entries/{entry_id}.md",
        "data": f"data/entries/{entry_id}.json",
    }

    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(page, encoding="utf-8")
    index.append(index_entry)
    index.sort(key=lambda entry: entry["entry_id"])
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"created {json_path.relative_to(ROOT)}")
    print(f"created {md_path.relative_to(ROOT)}")
    print(f"created {html_path.relative_to(ROOT)}")
    print("updated data/research-index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
