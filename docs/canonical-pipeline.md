# Fieldnotes Canonical Pipeline

Updated: 2026-09-08

This document is the authoritative map of the Fieldnotes system. Other runbooks and status
documents may explain one lane in more detail, but they must not contradict the ownership and
durability rules below.

## 1. Source-of-truth map

| Concern | Canonical source | Derived / runtime copy |
|---|---|---|
| repository | `/Volumes/DevDrive/Projects/fieldnotes` | `~/HermesWorkspace/project/fieldnotes-runtime` is a non-Git execution mirror |
| daily automation policy | `config/automation.json` | private runtime mirror |
| search profiles / next-search selection | `config/search-profiles.json` | private console edits the runtime copy; `runtime_sync.py pull/push` reconciles to canonical |
| discovery method | `docs/search-protocol.md` | daily prompt applies it |
| dated research result | `data/entries/YYYY-MM-DD-NN.json` | `docs/entries/` and `entries/` are human/presentation views |
| persistent seen-work registry | `data/work-index.json` | rebuilt from dated entries and registry |
| acquisition/work registry | `data/work-registry.json` | workspace state beneath the matching work directory |
| private Japanese source | `workspace/.../source*` and `merged/ja.txt` | never published |
| resumable translation queue | `workspace/.../translation/manifest.json` | public status is a sanitized projection only |
| exact translation work order | `workspace/.../translation/tasks/<chunk>.json` | one immutable task per chunk; contains source, segment ids, local proof, glossary/context |
| immutable translation result receipt | `workspace/automation-runs/backend/<work>/<role>/<operation>.worker-result.json` | created by the trusted driver after operation/work envelope validation; create-only, never an overwrite; full translation validation follows before canonical commit |
| translation glossary | `workspace/.../glossary.json` | Project conversation context is secondary evidence, never canonical state |
| Project-wide translation rules | `templates/project-context/` | immutable generated Project Source revisions under `workspace/project-context/` |
| final reading artifact | `workspace/.../translation/output/<원문 제목> - 번역본.txt` | private console/Tailnet download surface |
| user taste learning | `workspace/preference-feedback.json`, `workspace/preference-model.json` | soft ranking only |
| operational/discovery lessons | `workspace/learning/operational-lessons.json` | private runtime mirror; policy/schema lives in `config/learning-policy.json` |
| public site | GitHub Pages from tracked metadata/code | no source or translated fulltext |

The canonical repository is always the DevDrive checkout. The runtime mirror is writable because
the phone/private console needs an internal-volume process, but it is not a second source of truth.
The runtime marker stores the last synchronized hash for every mutable file/tree. A sync imports a
runtime-only change, pushes a canonical-only change, and refuses to overwrite either side when both
diverged from the last synchronized hash. This prevents both lost phone edits and mtime-based
rollback of an intentional canonical change.

## 2. Discovery pipeline

```text
private console search profile
    -> runtime_sync pull
    -> select_search_profiles.py --commit
    -> request-scoped discovery using search-protocol.md
    -> structured metadata / hard filters / seen-index dedupe
    -> adaptive body sampling of strongest survivors
    -> dated entry JSON (canonical result)
    -> rebuild work-index
    -> top-N registration + first-five private acquisition
```

Rules:

- Every new search starts from its own profile/request snapshot. Prior entry filters do not leak.
- Explicit current criteria outrank every learned signal.
- User taste is only a second-stage ranking prior after hard filters.
- `data/work-index.json` is consulted before expensive sampling/ranking.
- If no explicit minimum length exists, 300k characters is the default main-lane floor; unusually
  strong shorter matches may survive only in the separate `LENGTH EXCEPTION` lane.
- Do not pad a shortlist with low-fit works merely to hit a requested default count.
- Every actionable candidate must keep its canonical URL in the JSON entry itself. HTML links are
  presentation, not pipeline input.

## 3. Acquisition and preparation

The normal shortlist lane acquires the first five public reader episodes only. Full-work download
is a separate explicit user-request lane.

```text
register_targets.py
    -> novel-download worker
    -> source_inbox
    -> normalize / merge
    -> glossary ruby seed
    -> paragraph-aware chunks (~9k target, 12k hard max)
    -> sentence-id map
    -> translation/tasks/<chunk>.json
```

Manual `source_inbox/` remains a fallback if acquisition is unavailable. Copyrighted source and
translation payloads stay gitignored and private.

## 4. Translation architecture

There is exactly one ChatGPT Project: **Fieldnotes**.

- One novel owns one Project conversation.
- Every chunk of that novel reuses the same conversation.
- Different novels never share a conversation.
- Logical common sources are GLOBAL_CONTEXT, translation rules and user instructions. The current
  provider schema stores the latter two with `WORK_`-prefixed generated source names, but they are
  still Project-wide common sources, not per-work sources.
- Work metadata, Japanese source, sentence ids, adjacent context, ruby evidence, glossary and the
  hidden local proof are read from the exact local task JSON named by the driver.
- The model has read-only permission for that exact task path only. The external driver owns every
  validation and filesystem write.
- The worker returns the complete result envelope exactly once. `ProjectBackend` first validates
  operation/work envelope identity and creates a new operation-specific `*.worker-result.json`
  transport receipt with create-only filesystem semantics. The translation driver then validates
  local proof, Project Source proof, sentence alignment and glossary structure before any canonical
  chunk commit. The model never edits the task or creates/updates local result files itself.

Each translation result must prove both boundaries in the same model turn:

1. fresh proof for the exact Project Source revisions;
2. `local_source_proof` copied from the exact local task after the allowed Core read.

The result must then contain exactly one Korean row for every source sentence id in order. Missing,
extra, merged or reordered sentence ids fail validation.

## 5. Verified web-runner profile

The current production browser profile is deliberately conservative:

- maximum **2 distinct works** active at once;
- minimum **30 seconds** between new launches;
- chunks inside one work are strictly sequential;
- existing/revivable work conversations are preferred before opening a new work;
- Project status polling defaults to **3 seconds**;
- completed work conversation tabs are closed by exact conversation id;
- the Fieldnotes Project landing tab may remain open.

The 2026-09-07 seven-work E2E completed 16/16 chunks. A clean stable segment of the final runner
completed 6 chunks in 870.75 seconds with no failures. Normal primary-only chunks were generally
about 2–3.5 minutes; malformed JSON repair can make a chunk materially longer.

## 6. Failure and recovery semantics

Durability comes before throughput.

- `rate_limited` from the local Steroids loopback bridge is pre-route throttling. Retry the same
  local request with bounded backoff; do not create a replacement model operation.
- Provider `CHATGPT_CONVERSATION_RATE_LIMITED` stops new scheduling globally.
- An accepted operation is never resubmitted merely because the local waiter timed out.
- A timed-out accepted operation becomes retryable only after authenticated Steroids recovery
  targets the exact worker generation and exact bound conversation, clicks ChatGPT's own Stop
  control, proves generation ended, and returns a durable `remoteStopped:true` receipt. Only then
  may Fieldnotes mark that operation `interrupted` and revive the same conversation for the same
  operation. A failed/unproven interrupt changes no worker or operation state.
- An identityless uncertain spawn is retryable only if an exact broker status read proves that no
  worker exists for the target.
- `INVALID_MODEL_JSON` gets at most one same-conversation JSON-syntax repair. The repair may not
  reread source or retranslate.
- A glossary value conflict keeps the existing canonical value and records the proposal as a
  review decision; structural glossary errors still fail closed.
- Fallback is allowed only for the explicit codes in `config/project-translation.json`. Ambiguous
  delivery, source/hash changes and commit uncertainty never trigger automatic fallback.

Verified patterns above are also stored as active private operational lessons. New failure
signatures begin as observations and are not promoted until a fix passes regression/E2E evidence.

## 7. Learning loops

Fieldnotes has two separate learning systems.

### Taste learning

User ratings/reasons/notes learn preference signals. They may rerank hard-filter survivors and
suggest soft-preference changes. They never rewrite explicit hard filters automatically.

### Operational/discovery learning

`scripts/learning_store.py` maintains a private evidence ledger for recurring failure signatures,
verified fixes and search-process lessons.

```bash
python3 scripts/learning_store.py seed
python3 scripts/learning_store.py context --domain translation
python3 scripts/learning_store.py context --domain discovery
python3 scripts/learning_store.py record --domain discovery --signature "..." --outcome observed
```

Only lessons with a verified resolution become active context. Regressions reduce confidence and
can demote a lesson back to observed. The store must never contain source text, translated chapter
text, complete model answers, credentials or private URLs.

## 8. Output and delivery

After every chunk commits transactionally, the final work build emits:

- `ko.txt`
- `ja-ko.md`
- `<원문 제목> - 번역본.txt`
- `<work-id>-translation.zip`

The user-facing TXT groups consecutive source sentences by original paragraph, then places the
corresponding Korean paragraph immediately after it. It does not print `원문:`/`번역:` labels.
Sentence-level ids remain the internal validation unit.

Private runtime delivery is through loopback `127.0.0.1:18765` behind Tailscale Serve. GitHub Pages
contains metadata/UI only.

## 9. Current next-search input contract

The private console is the writable search-control surface. A search group is runnable when it is
enabled and either explicitly selected for the next run or eligible under the configured fallback
rotation. The private page now autosaves profile edits and selection changes; checking **다음 탐색**
also activates the group before writing it.

The public GitHub Pages console is intentionally read-only. Typing/selecting search criteria must
be done on the Tailnet private console if the change is expected to reach the canonical pipeline.

## 2026-09-08 review verification amendments

The ranker enforces the default 300k minimum even if omitted and consumes a truthful failed
minimum receipt in the explicitly authorized default-length exception lane. Both result buckets
retain a single frozen preference_rank order through registration and Daily Taste. Seen-index
checks run before rank-time sample verification; the discovery worker must still invoke the index
before initial expensive acquisition, which cannot be proved by a later ranking receipt.

Profile writers share transaction locks and Console revisions prevent stale page overwrites.
Immutable runtime evidence merges as a union; coupled mutable-state conflicts still stop the
refresh until an exact, backed-up, compare-and-swap resolution. Detailed verification is in
`pipeline-harness-review-verification.md`.
