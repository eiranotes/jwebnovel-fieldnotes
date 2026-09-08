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

### D015 — Translation source stays local and workers read one immutable task artifact
Copyrighted chapter text is no longer serialized into the Project-worker chat payload. The driver sends an absolute, workspace-fenced reference plus SHA-256 for the canonical `translation/tasks/<chunk>.json`; a `translate_chunk` worker may use Chat On Steroids Core `read` on that exact path only. The task file carries the source text, sentence ids, adjacent context, glossary and a stable random `local_source_probe` that is never sent in the prompt. A translation result is rejected unless it returns that hidden probe, so a model cannot satisfy the commit contract merely by claiming that it read the local file. Project Source verification remains a separate no-local-tools proof path.

## 2026-09-07

### D016 — One Fieldnotes Project, one conversation per work
All works share the single `Fieldnotes` ChatGPT Project. Project Sources contain only common workflow/translation/user rules. Work-specific text, glossary, ruby and context stay in the exact local task JSON. A work reuses one Project conversation across chunks; different works never share a conversation.

### D017 — Project proof and translation share one model turn
The translation result itself returns fresh proof for the exact common Project Source revisions plus the hidden local-task proof. A separate Project-source probe turn is not required on the production chunk path.

### D018 — Web transport is globally conservative
Production browser translation runs at no more than two distinct works concurrently, with at least 30 seconds between new launches and 3-second Project polling. Existing work conversations are preferred before opening another work. Completed work tabs are closed only by exact conversation id.

### D019 — Ambiguity is durable; only provable pre-send failures retry
Accepted or possibly submitted model work is never repeated because of timeout or transport uncertainty. An identityless uncertain spawn is retryable only when an exact broker status read proves no worker exists for that target. Provider rate limits stop new scheduling globally.

### D020 — Output-format and glossary repair are local, bounded operations
Malformed model JSON gets one same-conversation syntax-only repair turn without source reread/retranslation. Conflicting glossary proposals do not invalidate otherwise valid translations: the existing canonical glossary value wins and the proposal is stored as a conflict decision. Structural invalidity still fails closed.

### D021 — Operational/discovery learning is an evidence ledger, not free-form memory
Recurring translation/runtime failures and discovery-process mistakes are stored privately in `workspace/learning/operational-lessons.json`. New signatures start as observed; only verified resolutions become active. Regressions reduce confidence and can demote a lesson. User taste learning remains a separate soft-ranking system.

### D022 — Runtime refresh preserves phone edits before deployment
`runtime_sync.py` uses a last-synchronized content-hash ledger for mutable files/trees. Runtime-only edits are imported, canonical-only edits are pushed, and two-sided divergence becomes an explicit conflict instead of an mtime winner. `workspace/learning/` is included in the mutable private sync set. The private search console autosaves profile edits/selection and checking `다음 탐색` automatically enables that profile; GitHub Pages remains read-only.

## 2026-09-08

### D023 — Translation result files are driver-created, create-only receipts
The Project worker is read-only with respect to the local filesystem. It reads only the exact hash-validated local translation task and returns the requested result envelope exactly once. After operation/work envelope identity is validated, the trusted Fieldnotes backend creates `workspace/automation-runs/backend/<work>/<role>/<operation>.worker-result.json` with exclusive-create semantics as a transport receipt. The translation driver still performs Project Source proof, local proof, sentence-alignment and glossary validation before canonical chunk commit. Existing identical receipt content is idempotent recovery; conflicting existing content is a hard failure. The model never edits the task or creates/overwrites a local result file.

### D024 — Timeout retry requires exact remote-Stop proof
A waiter timeout never authorizes resubmission. Recovery may retry the same operation only after Steroids targets the exact worker id, creation generation and bound Project conversation, uses ChatGPT's own Stop control, and durably proves the turn ended. Fieldnotes then records the operation as `interrupted` and revives that same conversation. If Stop cannot be proved, both worker state and operation state remain blocked rather than guessing.

### D025 — Worker tabs live through result capture, not merely send acceptance
A Project worker tab may be closed only after the final model answer has been captured and the trusted local result/commit path has succeeded. Conversation bind or send acceptance alone is not the cleanup boundary because local Core calls and final transcript capture still depend on the page lifetime. Finished worker tabs are closed by exact conversation identity; arbitrary ChatGPT tabs are never bulk-closed.
