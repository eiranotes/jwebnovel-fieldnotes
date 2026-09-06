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
