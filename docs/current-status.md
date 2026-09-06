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
| automatic third-party body download | **not implemented by policy/platform constraint** |
| source inbox / normalize / merge | implemented |
| resumable chunk queue | implemented |
| glossary / proper-name continuity | implemented |
| local JA/KO parallel viewer | implemented |
| public fulltext publishing | disabled |
| GitHub Pages automation status | implemented |

## Source pipeline targets — 2026-09-06-02

| Rank | Work | Status | Workspace |
|---|---|---|---|
| A1 | 紅さんはデスゲーマー | waiting_for_source | `workspace/2026-09-06/2026-09-06-02/beni-death-gamer/` |
| A2 | 拝啓、明日ノ私〜才能で選別される狂気のデスゲーム〜 | waiting_for_source | `workspace/2026-09-06/2026-09-06-02/haikei-ashita-no-watashi/` |
| B1 | Redo -リドゥ- | waiting_for_source | `workspace/2026-09-06/2026-09-06-02/redo/` |
| A-LE1 | 逆さの茶笠 | waiting_for_source | `workspace/2026-09-06/2026-09-06-02/sakasano-chagasa/` |
| B-LE1 | デスゲーム界の十傑 | waiting_for_source | `workspace/2026-09-06/2026-09-06-02/deathgame-jikketsu/` |

Each work has tracked `metadata.json` and `state.json`. Put lawful/user-supplied TXT/ZIP into its `source_inbox/`; that directory and all source/translation fulltext are gitignored.

## Required before enabling the daily automation

1. Answer `docs/automation-questionnaire.md`.
2. Supply exact daily clock time in Asia/Seoul.
3. Convert answers into `config/search-profiles.json` and set `criteria_ready=true`.
4. Set `config/automation.json` → `enabled=true`, `time="HH:MM"`.
5. Create the ChatGPT daily scheduled task with `docs/daily-automation-prompt.md` as the execution contract.

## Current blocker detail

The discovery/page pipeline can run unattended once profiles/time are configured. The **body acquisition step cannot be unattended for third-party Narou/Kakuyomu works** under the verified current platform constraints. It is intentionally a source-inbox gate. Everything after that gate is automated and resumable.
