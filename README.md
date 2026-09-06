# Japanese Web Novel Field Notes

나로우(小説家になろう)와 카쿠요무에서 장편 작품을 찾을 때, **요청 당시의 기준작·제외조건·문체 요구를 그대로 보존하면서 날짜별로 결과를 누적**하는 리서치 저장소.

이 저장소의 단위는 “추천 목록”이 아니라 **research entry**다. 기준작이나 요구조건이 바뀌면 이전 결과를 덮어쓰지 않고 새 엔트리를 만든다.

## Entry rule

엔트리 ID는 `YYYY-MM-DD-NN` 형식을 쓴다.

- `2026-09-06-01` — 2026-09-06의 첫 조사
- 같은 날 별도 요청이 생기면 `2026-09-06-02`
- 기존 조사 조건을 좁히거나 확장한 후속 조사에는 `continuation_of`를 기록
- 새 기준작이나 새 요구조건이면 같은 날짜라도 별도 엔트리

각 엔트리는 최소한 다음을 보존한다.

1. 사용자가 요청한 조건의 원문 요약
2. 기준작 / 반례작과 각 작품의 역할
3. 필수조건, 제외조건, 선호조건, 허용 예외
4. 그 요청에서 사용한 문체·전개 평가축과 가중치
5. 후보 수집 경로와 본문 샘플 위치
6. 통과작 / 대기작 / 제외작과 제외 이유
7. 출판 여부 확인 수준과 확인일

## Default length policy

사용자가 별도 분량을 지정하지 않으면 **300,000자 이상**을 기본 탐색 하한으로 쓴다.

- 사용자가 50만 자, 100만 자처럼 직접 지정한 값이 있으면 그 값이 우선한다.
- 30만 자 미만 작품은 기본 shortlist에서 제외한다.
- 단, **분량을 제외한 핵심 요구조건과 reference fingerprint가 모두 강하게 일치**하면 `LENGTH EXCEPTION`으로 별도 유지한다.
- length exception은 정상 분량 후보와 섞어 수량을 채우지 않는다.

## Current entries

### 2026-09-06-01 — 경파한 문체와 빠른 사건 전개

기준작: 『賢者フィロフィーと気苦労の絶えない悪魔之書』  
https://ncode.syosetu.com/n2066cv/

원래 요청은 50만 자 이상, 하이/로우 판타지, 전생·악역영애·게임 요소 제외, 비상위권, 비서적화, 연재중 우선. 이후 실제 본문 비교를 거쳐 **기능적이고 건조한 문장, 높은 사건 처리량, 비정상적 상황의 무감상 처리**가 핵심 기준으로 추가됐다.

### 2026-09-06-02 — 죽음이 일상이 된 플레이어들

기준작: 『死亡遊戯で飯を食う。』
이번 엔트리는 앞선 01 조건을 상속하지 않고, **반복되는 데스게임의 직업성·숙련자의 룰/자원 계산·게임 사이 관계 누적**을 새 fingerprint로 사용했다. 같은 날짜의 독립 조사는 날짜 아래 `01`, `02`, `03`처럼 함께 묶인다.

## Repository map

- `data/research-index.json` — 날짜별 조사 인덱스. GitHub Pages archive의 원본
- `data/entries/YYYY-MM-DD-NN.json` — 요청·기준·결과를 기계적으로 읽을 수 있는 엔트리 데이터
- `docs/entries/YYYY-MM-DD-NN.md` — 사람이 읽는 조사 기록
- `entries/YYYY-MM-DD-NN.html` — 해당 날짜 조사 페이지
- `docs/search-protocol.md` — 요청과 무관하게 재사용하는 탐색 프로토콜
- `docs/entry-format.md` — 엔트리 스키마와 판정 필드 정의
- `templates/research-request.json` — 다음 요청을 구조화할 때 쓰는 템플릿
- `scripts/new_entry.py` — 날짜별 다음 sequence의 조사 뼈대를 생성
- `index.html` — 날짜별 archive

## Classification

- `A` — 요청의 hard gate를 통과하고, 기준작/요구 문체에 강하게 근접
- `B` — hard gate는 통과하지만 특정 축에서만 강한 참고작
- `Q` — 메타데이터 통과, 본문 또는 출판 교차검증 대기
- `D` — 직접 읽은 뒤 해당 요청 기준에서 우선순위를 낮춘 작품
- `X` — hard gate 위반으로 제외
- `A-LE / B-LE` — 기본 30만 자에는 미달하지만 분량 외 핵심 조건이 강하게 일치한 length exception

## Publication wording

`미출판`을 단정하지 않는다. `P0–P3` 확인 수준을 쓴다.

- `P0` 미확인
- `P1` 작품 페이지에서 상업판 표시를 찾지 못함
- `P2` 작품 페이지 + 제목/작가 외부 검색에서도 상업판을 찾지 못함
- `P3` 상업출판 확인 — 비출판 조건이 있으면 제외

현재 프로토콜은 `docs/search-protocol.md`의 **v0.4**를 따른다. 과거 엔트리에 기록된 점수·판정은 당시 조사 기록이므로 소급 변경하지 않는다.

## Daily automation

Daily discovery/translation automation scaffolding lives in:

- `docs/automation-questionnaire.md` — inputs still needed from the user
- `docs/automation-decisions.md` — implementation decisions and platform boundaries
- `docs/decision-log.md` — chronological decisions
- `docs/automation-runbook.md` — source/merge/chunk/translation commands
- `docs/daily-automation-prompt.md` — execution contract for the scheduled ChatGPT/Steroids job
- `docs/current-status.md` — current blockers and top-5 work paths
- `data/work-registry.json` — machine-readable work path/status registry

The acquisition worker is bundled at `workers/novel-download/` in this same repository. `scripts/full_pipeline.py` bridges finalized research entries into that worker, then hands the resulting first-N source files back to the merge/chunk/glossary pipeline. `scripts/translation_queue.py` provides one global oldest-pending-first queue across all registered works.

The actual daily scheduled job is intentionally not enabled until the exact Asia/Seoul clock time and at least one completed search profile are supplied.
