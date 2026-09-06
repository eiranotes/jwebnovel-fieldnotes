# Research Entry Format

각 조사 요청은 독립적인 `research entry`다.

archive용 `research-index.json`에는 `criteria_terms[]`도 넣는다. 사용자가 나중에 기준작 이름뿐 아니라 `전생 제외`, `비출판`, `빠른 전개` 같은 당시 요구조건으로도 과거 조사를 찾기 위한 필드다.

## ID

```text
YYYY-MM-DD-NN
```

같은 날짜의 두 번째 별도 요청은 `-02`. 기존 조사 연장이라면 새 엔트리를 만들고 `continuation_of`를 설정한다.

## Request snapshot

검색 전에 아래 네 종류로 나눈다.

- `MUST` — 어기면 제외
- `MUST NOT` — 명시적 금지 요소
- `PREFER` — 우선하지만 필수 아님
- `TOLERATE` — 허용 예외

## Reference

- `reference_works[]` — 닮아야 할 기준
- `anti_reference_works[]` — 피해야 할 기준

기준작이 없으면 사용자의 자연어 요구에서 style dimensions를 직접 만든다.

## Result fields

각 후보는 다음을 분리한다.

- `eligibility`
- `style_distance`
- `visibility_band`
- `publication_tier`
- `confidence`
- `samples_read[]`
- `kept_because`
- `differs_because`

## Publication tier

- `P0` 미확인
- `P1` 작품 페이지에서 상업판 표기 미발견
- `P2` 작품 페이지 + 제목/작가 교차검색에서도 미발견
- `P3` 상업판 확인

## Classification

- `A` 요청과 매우 가까운 통과작
- `B` 일부 축에서 유용한 통과작
- `Q` 추가검증 대기
- `D` 읽은 뒤 우선순위 하향
- `X` hard filter 위반

## Scaffold

```bash
python3 scripts/new_entry.py --date 2026-09-06 --title "조사 제목" --dry-run
python3 scripts/new_entry.py --date 2026-09-06 --title "조사 제목"
```

`--continuation-of 2026-09-06-01`을 주면 이전 조사 연장임을 기록한다.
