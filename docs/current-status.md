# Current Automation Status

Updated: 2026-09-07

## Overall

| Item | State |
|---|---|
| dated archive | implemented |
| same-day multiple entries | implemented |
| default 300k + high-fit length exception | implemented |
| search profile config | implemented, awaiting answers |
| daily ChatGPT/Steroids job contract | implemented |
| exact daily schedule | **blocked: clock time not supplied** |
| Narou metadata discovery | official API lane |
| Kakuyomu discovery | current web metadata/search lane |
| automatic first-5 public episode acquisition | implemented through `novel-daily-pipeline` worker |
| source inbox / normalize / merge | implemented |
| resumable chunk queue | implemented |
| glossary / proper-name continuity | implemented |
| ChatGPT Project translation backend | **verified live; one Project chat per work, source-proof required** |
| Project retrieval anchor | **verified live: stable `GLOBAL_CONTEXT`; work-specific context comes from exact local task read** |
| private source transport | **verified live: exact Core `read` of local task; chapter text omitted from chat payload** |
| fresh Project chat bootstrap | **verified live after stale generated-draft recovery fix** |
| translation fallback | **verified live: local Codex planner → throwaway-profile Oracle/WebGPT → same validator/commit path** |
| translation output naming | **`<원문 제목> - 번역본.txt` for sentence-alternating JA/KO output** |
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

Current Project translation state: **10 completed chunks, 0 pending chunks**. All five source-pipeline candidates are complete: `beni-death-gamer` 2/2, `haikei-ashita-no-watashi` 3/3, `redo` 2/2, `deathgame-jikketsu` 1/1 and `sakasano-chagasa` 2/2.

Translation transport now keeps private chapter content in the gitignored local task JSON. The WebGPT task contains only an exact absolute path, its SHA-256, the stable Project retrieval anchor and the result contract. Work metadata, glossary and adjacent source context travel inside that exact local task rather than through a mutable per-work Project Source. Real production workers for `deathgame-jikketsu`, `redo` and `haikei-ashita-no-watashi` were recorded reading only their exact task file and then passed hidden local-source proof, Project-source proof, sentence alignment and transactional completion. The external driver still owns validation and all writes.

## Required before enabling the daily automation

1. Answer `docs/automation-questionnaire.md`.
2. Supply exact daily clock time in Asia/Seoul.
3. Convert answers into `config/search-profiles.json` and set `criteria_ready=true`.
4. Set `config/automation.json` → `enabled=true`, `time="HH:MM"`.
5. Create the ChatGPT daily scheduled task with `docs/daily-automation-prompt.md` as the execution contract.

## Current blocker detail

Discovery, target registration, first-five acquisition, source preparation, chunking, stable Project-source retrieval proof, exact local task reads, translation, transactional completion, private-runtime delivery and public status projection are connected. Final worker ownership is `(Project, work_id, role)`: the same work reuses its exact Project conversation and a different work creates a different conversation. Live isolation smoke created `fresh-chat-e2e-20260907a` as worker-43, reused worker-43 for its next turn, and created `fresh-chat-e2e-20260907b` separately as worker-44. The configured `codex_webgpt` fallback is allowed only for explicit terminal/pre-submit failure codes; ambiguous submission/timeouts stay blocked. Remaining configuration inputs for the scheduled daily job are still the final search profiles and exact daily schedule time.
