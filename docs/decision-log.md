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
