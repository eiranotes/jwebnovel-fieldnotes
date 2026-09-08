# Current Automation Status

Updated: 2026-09-08

## Overall

| Item | State |
|---|---|
| dated archive | implemented |
| same-day multiple entries | implemented |
| default 300k + high-fit length exception | implemented |
| search profile config | implemented; **`quiz-king-style` enabled and selected, criteria ready** |
| daily ChatGPT/Steroids job contract | implemented |
| exact daily schedule | **ready: daily 06:00 Asia/Seoul** |
| Narou metadata discovery | official API lane |
| Kakuyomu discovery | current web metadata/search lane |
| automatic first-5 public episode acquisition | implemented through `novel-daily-pipeline` worker |
| source inbox / normalize / merge | implemented |
| resumable chunk queue | implemented; **46 complete / 9 pending chunks** |
| glossary / proper-name continuity | implemented |
| ChatGPT Project translation backend | **verified live; one Fieldnotes Project, one Project chat per work** |
| Project Sources | **three common immutable sources; no per-work Project Source** |
| private source transport | **verified live: exact Core `read` of local task; chapter text omitted from chat payload** |
| translation result transport | **verified live: model returns one result envelope; trusted driver creates a new create-only operation result file (`driver_capture`)** |
| timed-out turn recovery | **verified live: exact worker/conversation remote Stop proof before same-operation same-chat retry** |
| fresh Project chat bootstrap | **verified live after stale generated-draft recovery fix** |
| translation fallback | **disabled in production; exhausted Codex account pool is not used automatically** |
| translation output naming | **`<원문 제목> - 번역본.txt` for sentence-alternating JA/KO output** |
| browser production runner | **verified: max 2 works, 30s launch gap, 3s Project polling** |
| operational/discovery learning | **implemented: private verified lesson ledger + seeded active lessons** |
| local JA/KO parallel viewer | implemented |
| public fulltext publishing | disabled |
| GitHub Pages automation status | implemented |

## Source pipeline targets — 2026-09-06-02

| Rank | Work | Status | Workspace |
|---|---|---|---|
| A1 | 紅さんはデスゲーマー | **translation_complete · 2/2 chunks** | `workspace/2026-09-06/2026-09-06-02/beni-death-gamer/` |
| A2 | 拝啓、明日ノ私〜才能で選別される狂気のデスゲーム〜 | **translation_complete · 3/3 chunks** | `workspace/2026-09-06/2026-09-06-02/haikei-ashita-no-watashi/` |
| B1 | Redo -リドゥ- | **translation_complete · 2/2 chunks** | `workspace/2026-09-06/2026-09-06-02/redo/` |
| A-LE1 | 逆さの茶笠 | **translation_complete · 2/2 chunks** (3 public episodes total) | `workspace/2026-09-06/2026-09-06-02/sakasano-chagasa/` |
| B-LE1 | デスゲーム界の十傑 | **translation_complete · 1/1 chunk** | `workspace/2026-09-06/2026-09-06-02/deathgame-jikketsu/` |

Each work has tracked `metadata.json` and `state.json`. The integrated runner writes the selected first five public episodes to `source_inbox/` and immediately prepares the local translation queue. Manual TXT/ZIP remains a fallback. Source/translation fulltext stays gitignored.

The earlier `2026-09-06-02` production set remains complete at **10/10 chunks**.

The later `2026-09-06-01` seven-work E2E is also complete at **16/16 chunks**: `narou-n5290ek` 2/2, `narou-n8361ja` 3/3, `narou-n8655kq` 3/3, `narou-n8514ea` 2/2, `narou-n9369ff` 2/2, `kakuyomu-16818622172225120257` 2/2, and `kakuyomu-16817330656026243259` 2/2. Combined verified sample-translation state across the two 2026-09-06 entries is **26 completed chunks / 0 pending chunks**.

Translation transport keeps private chapter content in the gitignored local task JSON. The WebGPT task contains only an exact absolute path, its SHA-256, the common Project Source revision descriptors and the result contract. Work metadata, glossary and adjacent source context travel inside that exact local task rather than through a mutable per-work Project Source. Project-source proof is returned inside the same translation result, so each chunk needs one model turn rather than a separate proof turn. The external driver still owns validation and all writes.

On 2026-09-08 the production path was hardened further: the model no longer attempts any local
write. After the single response envelope validates, `ProjectBackend` creates a new
operation-specific `*.worker-result.json` with exclusive-create semantics and records
`result_source=driver_capture`. A live recovery of `narou-n6584ll` chunk 0003 also proved the
timeout rule end to end: exact remote Stop was confirmed for the existing worker conversation,
the same operation was revived in that same conversation, the driver captured 327 validated
sentence rows, and the work completed 3/3 without opening a replacement work chat.

The 2026-09-07 E2E verified the current browser safety profile: two distinct works maximum, 30-second stagger between launches, 3-second Project polling, same-work sequential chunks, exact-conversation tab cleanup, local loopback 429 backoff, provider-rate-limit global stop, same-work JSON repair, and fail-closed uncertain-delivery handling.

`workspace/learning/operational-lessons.json` now accumulates verified translation/runtime and discovery lessons privately. `config/learning-policy.json` defines promotion and guardrails. User taste learning remains separate and can only soft-rerank hard-filter survivors.

## Current daily automation

The canonical status currently reports a ready daily schedule at **06:00 Asia/Seoul** with one
runnable search profile (`quiz-king-style`). `data/automation-status.json` is the status projection;
`config/automation.json` and `config/search-profiles.json` remain the canonical configuration.

## Current blocker detail

Discovery, target registration, first-five acquisition, source preparation, chunking, common Project Source sync/proof, exact local task reads, translation, transactional completion, private-runtime delivery and public status projection are connected. Final worker ownership is `(Project, work_id, role)`: the same work reuses its exact Project conversation and a different work creates a different conversation. The configured `codex_webgpt` fallback remains disabled for the current production backend. Ambiguous submission/timeouts stay blocked unless the exact remote-interrupt proof described above converts a timed-out accepted operation into a safe same-chat retry.

At the first 2026-09-07 22:05 KST check, the next-run resolver still returned no enabled profile. During the runtime-preserving deployment the private mutable state produced a newer saved profile named `퀴즈왕`, proving the user's input itself survived. Its recovered state was still the legacy placeholder id `example-disabled`, `enabled=false`, with no explicit selection, so it was **stored but not runnable**. The canonical profile was then normalized to a real enabled profile, its title+URL reference pair was normalized, and it was selected for the next run once. The private console now autosaves profile edits/selection and auto-enables a profile when `다음 탐색` is checked to prevent the same state mismatch. The public GitHub Pages console remains read-only.
