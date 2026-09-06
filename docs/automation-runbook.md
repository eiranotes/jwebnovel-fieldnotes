# Daily Automation Runbook

## Paths

| Purpose | Path |
|---|---|
| automation config | `config/automation.json` |
| search profiles | `config/search-profiles.json` |
| public status | `data/automation-status.json` |
| dated discoveries | `data/entries/`, `docs/entries/`, `entries/` |
| local work root | `workspace/YYYY-MM-DD/ENTRY_ID/WORK_ID/` |
| source drop | `.../source_inbox/` |
| merged Japanese | `.../merged/ja.txt` |
| glossary | `.../glossary.json` |
| translation manifest | `.../translation/manifest.json` |
| chunk source/KO | `.../translation/chunks/NNNN/` |
| translation work orders | `.../translation/tasks/` |
| private parallel viewer | `.../translation/parallel/index.html` |
| persistent work index | `data/work-index.json` |
| automation log summary | `data/automation-logs.json` |
| private detailed logs | `workspace/automation-logs/YYYY-MM-DD.jsonl` |
| full-work translation root | `workspace/full-translations/WORK_ID/` |

## Register top-N targets

After a dated entry is finalized:

```bash
python3 scripts/register_targets.py --entry 2026-09-06-02 --top-n 5
```

This creates/updates tracked work metadata/state and `data/work-registry.json` without acquiring body text.

## Automatic top-N source acquisition + preparation

After an entry is finalized, run:

```bash
python3 scripts/full_pipeline.py \
  --entry 2026-09-06-02 \
  --top-n 5 \
  --episodes 5
```

This performs `register targets -> first N public episodes -> source_inbox -> normalize/merge -> chunk manifest -> glossary -> parallel-view scaffold`.

The acquisition worker is bundled at `workers/novel-download/` inside this repository. Override it with `--worker-root` or `NOVEL_PIPELINE_ROOT` only when intentionally testing another worker checkout.

Re-running the command reuses an unchanged `acquisition_manifest.json`; use `--force` only when a fresh first-N capture is required.

## Manual source preparation fallback

```bash
python3 scripts/source_pipeline.py prepare \
  --entry 2026-09-06-02 \
  --work beni-death-gamer \
  --title "紅さんはデスゲーマー" \
  --platform Kakuyomu
```

For a manually supplied source, put `.txt`, `.md`, or `.zip` into:

```text
workspace/2026-09-06/2026-09-06-02/beni-death-gamer/source_inbox/
```

`prepare` extracts TXT/MD, normalizes, merges, chunks, and creates state/glossary files.

## Next translation task

Across all works, use the global queue:

```bash
python3 scripts/translation_queue.py next
```

It selects the oldest pending work/chunk and emits the full translation task JSON, including source, neighboring context, glossary, and the task path.

Per-work fallback:

```bash
python3 scripts/source_pipeline.py next-task \
  --entry 2026-09-06-02 \
  --work beni-death-gamer
```

The returned task JSON contains:

- full current Japanese chunk
- previous Japanese tail
- next Japanese head
- current glossary
- strict output contract

ChatGPT translates it and writes a result JSON with `ko_text` and `glossary_update`.

## Complete a chunk

For the global queue path:

```bash
python3 scripts/translation_queue.py complete \
  --entry 2026-09-06-02 \
  --work beni-death-gamer \
  --chunk 0001 \
  --result /path/to/result-0001.json
```

This also rebuilds the local parallel view and refreshes global automation status.

Per-work fallback:

```bash
python3 scripts/source_pipeline.py complete \
  --entry 2026-09-06-02 \
  --work beni-death-gamer \
  --chunk 0001 \
  --result /path/to/result-0001.json
```

This updates chunk metadata, manifest, glossary, and work state.

## Build local original/translation view

```bash
python3 scripts/source_pipeline.py build-parallel \
  --entry 2026-09-06-02 \
  --work beni-death-gamer
```

The generated HTML is intentionally gitignored.

## Scheduling

Exact daily time is required before activation.

1. Fill `config/automation.json` → `time: "HH:MM"`, `enabled: true`.
2. Fill at least one profile in `config/search-profiles.json`; set `criteria_ready: true`.
3. Create the ChatGPT daily automation with `docs/daily-automation-prompt.md` as its execution contract.
4. Optional Mac-local state heartbeat: `python3 scripts/install_launchd.py`.

The ChatGPT automation is the important scheduler because discovery and translation require model/web capabilities. `launchd` alone cannot perform those steps.

## Search profile selection

The private console writes `config/search-profiles.json`. Resolve the next run with:

```bash
python3 scripts/select_search_profiles.py --commit
```

Explicitly checked groups all run. With no explicit selection the fallback can be `round_robin`, `least_recently_run`, `random_daily`, or `all_enabled`.

Before ranking discovery candidates, rebuild and consult the seen index:

```bash
python3 scripts/rebuild_work_index.py
cat candidates.json | python3 scripts/work_index.py --unseen-only
```

## Full-work translation

The private console's **전체 번역** action queues a work. CLI equivalent:

```bash
python3 scripts/full_translation.py request --key 'title-author:...'
python3 scripts/full_translation.py run-next
python3 scripts/full_translation.py next-task
```

This route is separate from the five-episode sample workspace. It acquires all currently listed episodes, merges the whole source, chunks it, then creates `ko.txt`, `ja-ko.md`, and a ZIP after every chunk is translated.

## Private console / phone downloads

Run locally:

```bash
python3 scripts/install_private_console.py
```

The server binds only to `127.0.0.1:18765`. The installer starts or reuses a detached user-session process and adds a Tailscale Serve path without replacing existing routes:

`https://tofu-macbookair.tail05abcf.ts.net/fieldnotes/console.html`

From an iPhone on the same tailnet, the **파일받기** tab downloads completed private translation artifacts directly from the Mac. GitHub Pages never receives those full-text files.

On this Mac, `launchd` is blocked by macOS privacy from reading the project on the external DevDrive (`Operation not permitted`). The project and dependencies stay on DevDrive, so reboot auto-start is intentionally not faked. After a Mac reboot, run `python3 scripts/install_private_console.py` once from an interactive user session; the console then remains available while the Mac is running.
