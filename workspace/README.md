# Local Workspace

This tree holds per-entry/per-work state. Metadata and manifests may be committed, but source text, merged Japanese text, translated text, and generated parallel-reading pages are ignored by Git.

Canonical layout:

```text
workspace/YYYY-MM-DD/ENTRY_ID/WORK_ID/
  metadata.json
  state.json
  glossary.json
  source_inbox/          # user-supplied/manual lawful source files; gitignored
  source/                # normalized/extracted source; gitignored
  merged/ja.txt          # gitignored
  translation/
    manifest.json
    chunks/0001/meta.json
    chunks/0001/ja.txt   # gitignored
    chunks/0001/ko.txt   # gitignored
    tasks/               # generated translation work orders; gitignored
    parallel/            # local HTML; gitignored
```
