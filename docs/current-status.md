# Current Automation Status

Updated: 2026-09-06

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
| local JA/KO parallel viewer | implemented |
| public fulltext publishing | disabled |
| GitHub Pages automation status | implemented |

## Source pipeline targets — 2026-09-06-02

| Rank | Work | Status | Workspace |
|---|---|---|---|
| A1 | 紅さんはデスゲーマー | translation_pending · 2 chunks | `workspace/2026-09-06/2026-09-06-02/beni-death-gamer/` |
| A2 | 拝啓、明日ノ私〜才能で選別される狂気のデスゲーム〜 | translation_pending · 3 chunks | `workspace/2026-09-06/2026-09-06-02/haikei-ashita-no-watashi/` |
| B1 | Redo -リドゥ- | translation_pending · 2 chunks | `workspace/2026-09-06/2026-09-06-02/redo/` |
| A-LE1 | 逆さの茶笠 | translation_pending · 2 chunks (3 public episodes total) | `workspace/2026-09-06/2026-09-06-02/sakasano-chagasa/` |
| B-LE1 | デスゲーム界の十傑 | translation_pending · 1 chunk | `workspace/2026-09-06/2026-09-06-02/deathgame-jikketsu/` |

Each work has tracked `metadata.json` and `state.json`. The integrated runner writes the selected first five public episodes to `source_inbox/` and immediately prepares the local translation queue. Manual TXT/ZIP remains a fallback. Source/translation fulltext stays gitignored.

Current integrated smoke run: **5 works processed, 0 errors, 10 pending translation chunks**. Both Kakuyomu and Narou acquisition paths were exercised.

## Required before enabling the daily automation

1. Answer `docs/automation-questionnaire.md`.
2. Supply exact daily clock time in Asia/Seoul.
3. Convert answers into `config/search-profiles.json` and set `criteria_ready=true`.
4. Set `config/automation.json` → `enabled=true`, `time="HH:MM"`.
5. Create the ChatGPT daily scheduled task with `docs/daily-automation-prompt.md` as the execution contract.

## Current blocker detail

Discovery, target registration, first-five acquisition, source preparation, chunking and state updates are now connected. Remaining configuration inputs are the final search profiles, daily translation chunk cap, and the exact daily schedule time.
