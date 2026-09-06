from __future__ import annotations

import html
import os
from collections import Counter
from pathlib import Path

from .config import AppConfig
from .db import StateDB


def _artifact_link(config: AppConfig, row) -> str:
    root = config.pipeline.data_dir / "works" / row["site"] / row["work_id"]
    candidates = sorted((root / "bilingual").glob("ja-ko_*.md")) if (root / "bilingual").exists() else []
    if not candidates:
        candidates = sorted((root / "merged").glob("original_*.txt")) if (root / "merged").exists() else []
    if not candidates:
        return ""
    target = candidates[-1]
    rel = os.path.relpath(target, config.pipeline.site_dir)
    return Path(rel).as_posix()


def build_report(config: AppConfig, db: StateDB) -> Path:
    rows = list(db.list_works())
    counts = Counter(row["status"] for row in rows)
    total = len(rows)
    cards = "".join(
        f'<div class="card"><strong>{html.escape(status)}</strong><span>{count}</span></div>'
        for status, count in sorted(counts.items())
    )
    table_rows: list[str] = []
    for row in rows:
        artifact = _artifact_link(config, row)
        artifact_html = f'<a href="{html.escape(artifact)}">output</a>' if artifact else "-"
        error = html.escape((row["last_error"] or "")[:240])
        table_rows.append(
            "<tr>"
            f"<td>{html.escape(row['site'])}</td>"
            f"<td><a href=\"{html.escape(row['url'])}\">{html.escape(row['title'] or row['work_id'])}</a></td>"
            f"<td>{html.escape(row['author'] or '-')}</td>"
            f"<td>{int(row['episode_count'])}</td>"
            f"<td><code>{html.escape(row['status'])}</code></td>"
            f"<td>{html.escape(row['source_query'] or '-')}</td>"
            f"<td>{artifact_html}</td>"
            f"<td class=\"error\">{error}</td>"
            "</tr>"
        )

    page = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Novel Daily Pipeline</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f5f5f5;color:#171717}}
main{{max-width:1500px;margin:0 auto;padding:28px}}
h1{{font-size:24px;margin:0 0 6px}} .muted{{color:#6b6b6b;margin:0 0 22px}}
.cards{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}} .card{{background:white;border:1px solid #ddd;border-radius:9px;padding:12px 16px;min-width:130px}}
.card strong{{display:block;font-size:12px;color:#666}} .card span{{font-size:22px;font-weight:700}}
.table-wrap{{overflow:auto;background:white;border:1px solid #ddd;border-radius:10px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{padding:10px 12px;border-bottom:1px solid #eee;text-align:left;vertical-align:top;white-space:nowrap}}
th{{position:sticky;top:0;background:#fafafa}} td:nth-child(2){{white-space:normal;min-width:280px}} .error{{white-space:normal;max-width:360px;color:#9d2525}}
a{{color:#1557b0;text-decoration:none}} code{{font-size:12px}}
</style>
</head>
<body><main>
<h1>Novel Daily Pipeline</h1>
<p class="muted">총 {total}작품 · 신규 탐색/다운로드/번역 상태</p>
<div class="cards">{cards}</div>
<div class="table-wrap"><table>
<thead><tr><th>Site</th><th>Work</th><th>Author</th><th>Episodes</th><th>Status</th><th>Query</th><th>Artifact</th><th>Error</th></tr></thead>
<tbody>{''.join(table_rows)}</tbody>
</table></div>
</main></body></html>"""
    config.pipeline.site_dir.mkdir(parents=True, exist_ok=True)
    output = config.pipeline.site_dir / "index.html"
    output.write_text(page, encoding="utf-8")
    return output
