# Decision Log

## 2026-09-06

### D001 — Research entries are date-sequenced
Use `YYYY-MM-DD-NN`; several unrelated searches can coexist on one date.

### D002 — Search criteria are entry/profile scoped
Reference works and exclusions do not leak from one research request into the next.

### D003 — Default minimum length is 300,000 characters
Shorter works are excluded by default. A small number may remain as `LENGTH EXCEPTION` only when non-length core fit is unusually high.

### D004 — Daily automation is Steroids-first
ChatGPT performs current discovery/reasoning; Chat On Steroids Core owns repository reads/writes, state files, validation, git push, and durable work continuation.

### D005 — Selected first-N acquisition is integrated
The shortlist pipeline may capture only the selected work's first N public reader episodes into the private local workspace. Default N is 5. Full-work archiving is not part of this pipeline, and manual source inbox remains available as a fallback.

### D006 — Fulltext is private
Japanese source, Korean translation, translation tasks and parallel viewer are gitignored. Public GitHub Pages gets only metadata, findings and progress.

### D007 — Translation is resumable
Merged Japanese source is split at paragraph boundaries around 9k characters, hard max 12k. Each work stores manifest/checkpoints. Oldest pending work resumes first unless profile config says otherwise.

### D008 — Proper nouns are evidence-driven
Glossary is persistent across chunks. Metadata and ruby/furigana are preferred evidence. Aozora-style ruby found in merged source is automatically extracted into `glossary.ruby_notes` before translation.

### D009 — Schedule remains disabled until exact time and profiles are supplied
The user requested one run per day at a fixed time but has not supplied the clock time or final search profiles. No arbitrary time is invented.

### D010 — Search profiles are page-editable and independently selectable
`console.html` edits `config/search-profiles.json`. Multiple explicitly selected groups all run on the next discovery. With no explicit selection, fallback modes are round-robin, least-recently-run, date-seeded random, or all enabled; rotation state is durable.

### D011 — Seen works have a persistent canonical index
`data/work-index.json` records every previously surfaced candidate. Canonicalization prefers normalized title + author so Narou/Kakuyomu cross-posts collapse to one work; platform URL/ID is used when title/author evidence is insufficient. Strict discovery excludes already indexed works before sampling/ranking.

### D012 — User-selected full translation is a separate priority lane
The ordinary shortlist path stays first-5 only. A user's **전체 번역** action creates a separate `workspace/full-translations/<work-id>/` request, verifies the complete episode list, downloads all currently listed episodes, merges, chunks, resumes translation, then emits private `ko.txt`, `ja-ko.md`, and ZIP artifacts.

### D013 — Automation emits private detailed logs plus public-safe summaries
Every durable automation boundary writes JSONL under ignored `workspace/automation-logs/` and a sanitized rolling summary to `data/automation-logs.json`. The archive and private console expose those summaries without publishing source text.

### D014 — Phone delivery uses a loopback console behind Tailscale Serve
The private control server binds only to `127.0.0.1:18765`; Tailscale Serve exposes it at `/fieldnotes` on the user's tailnet. Direct `workspace/` browsing is denied and downloads use an artifact allowlist. macOS blocks `launchd` background access to this external DevDrive, so the server runs as a detached interactive-session process and must be restarted once after a Mac reboot.
