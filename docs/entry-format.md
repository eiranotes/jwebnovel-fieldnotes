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

## Length policy

사용자가 별도 최소 분량을 지정하지 않으면 전역 기본값은 **300,000자**다.

```json
{
  "source": "global_default",
  "default_min_chars": 300000,
  "explicit_min_chars": null,
  "effective_min_chars": 300000,
  "allow_high_fit_exception": true,
  "exception_label": "LENGTH EXCEPTION"
}
```

사용자가 직접 최소 분량을 지정하면 `source = user_explicit`으로 바꾸고 그 값을 `explicit_min_chars`와 `effective_min_chars`에 기록한다. 전역 30만 자 기준에만 미달하면서 분량 외 핵심 조건이 강하게 일치하는 작품은 `A-LE / B-LE`로 별도 저장한다.

## Reference

- `reference_works[]` — 닮아야 할 기준
- `anti_reference_works[]` — 피해야 할 기준

기준작이 없으면 사용자의 자연어 요구에서 style dimensions를 직접 만든다.

## Learning audit

- `learning_lessons_applied[]` — 이번 탐색에 실제로 적용한 active operational/discovery lesson id만 기록
- `discovery_incidents_observed[]` — 이번 탐색에서 새로 발견한 반복 가능 오탐/누락/수집 실패 signature를 기록

취향 모델의 raw event나 private lesson 본문을 엔트리에 복사하지 않는다. 엔트리는 어떤 검증된 lesson이 영향을 줬는지 id만 남겨 재현 가능하게 한다.

본문에서 측정한 feature는 private 후보 JSON과 trace에만 저장한다. 아래는 **형식 설명용 fixture**이며 실제 작품 평가가 아니다. sample 파일 내용은 `彼はすぐに扉を開いた。`(끝 개행 없음)이다. 실제 작업에서는 취득한 본문·출처와 그 SHA-256, frozen request hash, `canonical(candidate)`를 사용한다. 현재 요청의 모든 hard filter에 대응하는 receipt를 추가해야 한다.

```json
{
  "title": "Example (format fixture)",
  "url": "https://example.test/work",
  "length_chars": 300000,
  "base_score": 80,
  "eligible": true,
  "eligibility_receipt": {
    "request_hash": "<frozen request SHA-256>",
    "candidate_key": "<canonical(candidate)>",
    "checks": {
      "min_chars": {
        "status": "pass",
        "evidence": "metadata: 300000 chars",
        "source_url": "https://example.test/work"
      }
    }
  },
  "samples": [
    {
      "sample_id": "s0",
      "path": "workspace/review-samples/demo.txt",
      "sha256": "d35beb12cb93486200a9ddb2d8d514b466dfa8f5debaace40553f543c63f585c",
      "source_url": "https://example.test/work/1"
    }
  ],
  "preference_features": [
    {
      "atom": "pacing:fast",
      "value": 0.9,
      "confidence": 0.8,
      "sample_id": "s0",
      "start": 0,
      "end": 11,
      "evidence": "彼はすぐに扉を開いた。"
    }
  ]
}
```

`value`는 −1..1, `confidence`는 0..1, offset은 UTF-8 decode한 문자열의 문자 인덱스다. 인용은 본문의 exact substring이어야 한다. 요청·모델 점수·private feature는 공개 entry로 복사하지 않는다.

```bash
python3 scripts/preference_rank.py --profile PROFILE --context ENTRY_ID --request REQUEST.json --input CANDIDATES.json --count 5 --seed DATE:PROFILE:ENTRY_ID
python3 scripts/new_entry.py --finalize ENTRY_ID
```

점수는 `base_score + bounded additive shift`이며 72/28 혼합이 아니다. 현재 요청 차원을 mask하고 전체 적용 shift≤4, 단일 review 변경≤.5점을 강제한다. trace는 최초 생성만 가능하다. 새로운 결과를 원하면 새 context를 만든다.

기본 최소 분량은 요청에서 생략해도 300,000자다. 기본값의 예외만 `length_exception:{enabled:true,explicit_minimum:false}`로 허용하며, 후보의 `length_exception:true`, 정직한 `min_chars.status:fail` 및 출처를 가진 `length_exception_fit.status:pass`가 모두 필요하다. 사용자가 명시한 별도 최소값을 예외로 완화하지 않는다.

v2 공개 entry는 `shortlist`와 `length_exceptions`를 구분하되 두 버킷의 `preference_rank`가 하나의 frozen 순서를 나타낸다. downstream은 `selected_candidates(entry)`로 합친 뒤 top-N을 선택한다. 버킷 연결 순서로 top-N을 잘라서는 안 된다.

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
- `url` — shortlist/length exception처럼 downstream acquisition 대상이 될 수 있는 후보는 canonical HTTPS URL 필수

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
- `A-LE / B-LE` global 30만 자 기본값에만 미달한 고유사도 length exception

## Scaffold

```bash
python3 scripts/new_entry.py --date 2026-09-06 --title "조사 제목" --dry-run
python3 scripts/new_entry.py --date 2026-09-06 --title "조사 제목"
```

`--continuation-of 2026-09-06-01`을 주면 이전 조사 연장임을 기록한다.


## Schema 2 — preference evidence completion boundary (2026-09-08)

New entries have `status:draft`, a `profile_id`, and `preference_policy.required_trace:true`.
Freeze the analyzed request before discovery using `new_entry.py --freeze-request`; rank with the
v2 request/candidate/sample contract; then `new_entry.py --finalize` copies only safe metadata
from the frozen selected slate. Validators reject missing trace, changed request or reordered
shortlist. The four legacy entry IDs in `config/preference-policy.json` are excluded from this
new completion requirement and never receive fabricated prospective evidence.

Private trace/model/features/sample contents must not appear in public entry JSON. Public
`ranking_trace_hash` is an opaque content receipt, not the private trace itself.
