# Work Registry

Machine-readable source: `data/work-registry.json`.

## Path contract

For a work at `workspace/YYYY-MM-DD/ENTRY_ID/WORK_ID/`:

- `metadata.json` — work identity, URL, rank, source policy
- `state.json` — source/merge/translation progress
- `source_inbox/` — manually/user supplied source drop; **gitignored**
- `source/` — extracted/normalized files; **gitignored**
- `merged/ja.txt` — merged Japanese source; **gitignored**
- `glossary.json` — proper names, places, terms, ruby decisions
- `translation/manifest.json` — chunk ordering/status
- `translation/chunks/NNNN/ja.txt` — source chunk; **gitignored**
- `translation/chunks/NNNN/ko.txt` — Korean translation; **gitignored**
- `translation/tasks/` — resumable model work orders; **gitignored**
- `translation/parallel/index.html` — local original/translation viewer; **gitignored**

## Current registered works

See `docs/current-status.md` for the human-readable current table. New daily top-N targets are appended to `data/work-registry.json` and receive a workspace directory even if the source is not yet available.
