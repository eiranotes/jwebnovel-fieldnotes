# Fieldnotes 파이프라인·검색품질 하네스 독립 검토

작성일: 2026-09-08
대상: canonical working tree `/Volumes/DevDrive/Projects/fieldnotes` (main = `fa20c4e`, 미커밋 tracked 21 + untracked 13)
성격: `docs/preference-harness-audit.md`(구현자 자체 감사)와 별개의 2차 검토. 설계 문서를 구현의 증거로 취급하지 않고, 주장은 가능한 한 코드 실행으로 재현했다.

---

## 0. 범위와 방법

두 가지를 본다.

1. 발견 → 취득 → 번역 → 배포로 이어지는 canonical 파이프라인의 계약이 실제로 강제되는가
2. 검색품질 고도화용 취향 하네스가 "평가가 쌓일수록 검색이 좋아진다"를 **측정할 수 있는 구조**인가

각 항목은 아래 셋 중 하나로 표시한다.

- **[실행]** 코드를 직접 돌려 재현함
- **[독해]** 코드 독해로 판단함. 실행 재현은 하지 않음
- **[미검증]** 이번 범위에서 확인하지 못함

파일은 수정하지 않았고 커밋하지 않았다.

---

## 1. 판정 요약

**계약 설계는 견고하다.** 요청 freeze → 샘플 해시 검증 → immutable ranking trace → entry 검증 → target 등록으로 이어지는 경로가 fail-closed로 연결돼 있고, validator/gitignore의 private 증거 차단도 실제로 동작한다.

**그러나 하네스는 현재 형태로 목표에 도달할 수 없다.** 성능과 cohort 무효화 두 가지가 구조적으로 막고 있으며 둘 다 실측으로 재현했다. 또한 v2 경로는 **실사용 데이터로 한 번도 실행된 적이 없다.**

| 항목 | 상태 |
|---|---|
| 테스트 스위트 | **[실행]** `/usr/bin/python3 -m unittest discover -s tests` → 84 tests OK |
| 저장소 validator | **[실행]** `scripts/validate_repo.py` → ok |
| ranking trace 실적 | **[실행]** `workspace/preference-ranking-traces.json` contexts = **0개** |
| 실사용 entry | **[실행]** 4건 전부 schema 1.0/1.2, `config/preference-policy.json`의 legacy allowlist로 통과 |
| 취향 모델 실사용 state | **[실행]** 9 events / atom 11개 전부 tentative / prospective context 0 / applied L1 0.170564 / gate calibrating ×0.5 |
| runtime 미러 동기 상태 | **[실행]** 6개 항목 `runtime_ahead`, 충돌 0건 (현재 정상) |

즉 **"과잉반응 억제"는 실제로 잡혔고, "품질 개선 증명"은 시작조차 되지 않았다.** 구현자 감사문이 후자를 PASS라고 과장하지 않은 점은 정확하다.

---

## 2. 발견 사항

### P0-1. `record()`의 동기 rebuild가 O(N²)~O(N³) — 하네스가 성공할수록 못 쓰게 된다

**[실행]**

`preference_feedback.py:451`이 rebuild마다 **전체 operation 이력을 처음부터 재replay**하고, 각 스텝이 `_aggregate` 전체(`_pairwise` + 36 epoch 경사하강 + `_prospective_rank_metrics`)를 다시 돈다. 이 경로는 `private_console.save_taste_response` / `/api/feedback` **HTTP 핸들러 안에서 동기로** 실행된다.

합성 데이터 실측 (context당 5작품):

| reviews | trace 없음 | 유효 trace 있음 |
|---:|---:|---:|
| 40 | 0.09s | **1.15s** |
| 80 | 0.31s | **4.38s** |
| 160 | 1.09s | **18.43s** |
| 320 | 3.98s | **78.11s** |
| 640 | 15.87s | (미측정) |

더블링마다 약 4배. **prospective 데이터가 쌓이기 시작하는 바로 그 구간에서 비용이 터진다.** 수용기준인 20 contexts 시점에 이미 별점 한 번에 5~8초, 하루 1엔트리로 4개월이면 분 단위다.

증폭 원인 3개:

- `_pairwise_atom_model`(`:265`)과 `_prospective_rank_metrics`(`:300`)가 replay 스텝마다 `RANKING_TRACES`를 **디스크에서 재로드**
- `persist_trace`가 `model_snapshot`에 **모델 전체**를 넣는다(`preference_rank.py:120`). 모델은 리뷰당 약 1KB 선형 증가하므로 traces 파일이 `N_contexts × 모델크기`로 이차 증가하고 위 재로드 비용을 그대로 곱한다
- revision 아카이브가 매번 `source_files` 전체를 다시 쓴다(`:482`)

권장 수정: replay를 마지막 상태 기준 증분으로 전환하거나 revision 캐시 사용 / traces를 프로세스당 1회 로드로 캐시 / `model_snapshot`을 `model_revision` + `preference-revisions/<rev>.json` 포인터로 대체 / `record()`의 rebuild를 응답 경로에서 분리.

### P0-2. `code_revision()`이 축적된 prospective 증거를 통째로 무효화한다

**[실행]** — glob 대상 확인, **[독해]** — 무효화 경로

`preference_contract.py:137`은 trace의 `model_snapshot.code_revision`이 **현재** `code_revision()`과 다르면 그 pair를 prospective에서 제외한다. `preference_state.py:53`의 `code_revision()`은 다음 6개 파일 전체의 해시다.

```
scripts/preference_atoms.py     scripts/preference_contract.py
scripts/preference_evaluate.py  scripts/preference_feedback.py
scripts/preference_rank.py      scripts/preference_state.py
```

주석 한 줄, 새 `preference_*.py` 파일 추가, atomizer 규칙 1개 수정 — 무엇이든 하면 그때까지 모인 prospective context가 **전부 0으로 리셋**되고 gate가 `calibrating`(×0.5)으로 돌아간다.

`docs/TASKS.md`의 남은 수용기준(≥20 contexts, ≥60 pairs)을 채우려면 **preference 코드를 20일 이상 완전 동결**해야 한다. 개발이 진행 중인 상태에서는 사실상 도달 불가능한 게이트다.

권장 수정: cohort를 파일 해시가 아니라 명시적 `scoring_cohort_id`(수동 bump) 또는 점수에 실제로 영향을 주는 함수만의 해시로 좁힌다.

### P1-1. length_exception 계약 충돌 — 정직한 워커일수록 막힌다

**[실행]**

`preference_contract.py:85-88`의 required-check 루프가 `:97-102`의 예외 레인보다 먼저 돈다.

```
min_chars=300000, length_exception.enabled=true, 후보 120,000자 + length_exception_fit=pass
  worker가 정직하게 min_chars=fail → (False, 'missing_or_failed_check:min_chars')
  worker가        min_chars=pass → (True, 'pass')
```

**예외 레인에 도달하려면 워커가 체크를 허위로 기록해야 한다.** `canonical-pipeline.md` §2와 `new_entry.py`의 `length_policy.allow_high_fit_exception`이 규정한 LENGTH EXCEPTION 레인이 기계 계약 수준에서 닫혀 있다.

### P1-2. 300k 기본 하한이 코드에 없다 — 반대 방향 fail-open

**[실행]**

위와 같은 뿌리의 반대편 결함이다. `eligibility`(`preference_contract.py:93`)는 `hard_filters.min_chars`가 **선언됐을 때만** 길이를 본다. `new_entry.py:90`은 `min_chars: None`으로 스캐폴딩한다.

```
min_chars 미선언 → 12,000자 작품이 (True, 'pass')
min_chars=300000 → (False, 'length')
```

문서에서 가장 자주 인용되는 규칙인데 request/샘플/trace가 전부 fail-closed인 계약에서 여기만 fail-open이다. P1-1과 함께 **"길이 정책이 계약이 아니라 프롬프트에만 존재한다"**는 한 문제로 묶어 고쳐야 한다.

### P1-3. `config/search-profiles.json`에 writer 3개, 락 규율 3종

**[독해]**

| writer | 락 | 쓰기 방식 |
|---|---|---|
| `private_console.py:639,654` (`/api/profiles`, `/api/selection`) | 없음 | `atomic_write` (고정 `.tmp` 이름) |
| `select_search_profiles.py:64,72` | 없음 | 평문 `write_text` (비원자적) |
| `preference_feedback._apply_suggestion:550` | workspace 락 | `preference_state.save` |

셋 다 read-modify-write다. 콘솔이 "다음 탐색"을 저장하는 사이 데일리 잡의 `consume_explicit_selection`이 구버전 config를 덮어쓰면 사용자의 선택이 조용히 사라진다. `canonical-pipeline.md` §9가 콘솔을 유일한 검색제어 표면으로 규정한 것과 직접 충돌한다.

### P1-4. runtime_sync 충돌이 all-or-nothing이고 해소 수단이 없다

**[독해]** (현재 상태는 **[실행]**으로 정상 확인)

`runtime_sync.py:244-252` — 한 경로라도 양쪽 divergence면 **다른 모든 경로의 import까지 중단**하고 `conflict`를 반환한다. `_push`도 그 시점에 멈추므로 미러 갱신 전체가 정지한다.

그런데 `MUTABLE_WORKSPACE_DIRS`의 `workspace/preference-revisions`는 **평가할 때마다 런타임 쪽에, 데일리 잡이 돌 때마다 canonical 쪽에** 파일이 생기는 트리다. 트리 단위 해시라 양쪽 divergence가 되기 쉽고, 한번 걸리면 `--prefer` 같은 해소 명령이 없어 수동 개입 전까지 영구 교착이다.

현재 실측 상태는 정상 — 6개 항목 `runtime_ahead`, 충돌 0건.

### P1-5. `finalize_entry`가 LENGTH EXCEPTION 레인을 항상 비운다

**[독해]**

`preference_contract.py:186`이 `entry['results']['length_exceptions']=[]`를 무조건 실행한다. 현재 `2026-09-06-02`에 2건이 들어 있고, 이 엔트리가 v2로 마이그레이션되면 그 2개 작품은 공개 엔트리에서 삭제된다. `register_targets.py:60`과 daily prompt 18번은 두 버킷을 모두 읽으므로 계약이 어긋난다.

### P1-6. 원자화기가 한국어 활용형에서 abstain 대신 잘못된 차원으로 강등된다

**[실행]**

규칙이 음절 블록 리터럴이라 어미 변화를 놓치고, 놓치면 `unresolved`가 아니라 `GENERIC_ASPECTS` 폴백이 걸린다.

```
'전개가 빠르다'          → pacing:fast +      정상
'전개가 빨라서 좋았다'    → pacing:quality +   차원 소실
'전개가 빨랐다'          → (없음)             신호 유실
'문장이 잘 읽힌다'        → prose:quality +    '읽히' ≠ '읽힌'
'전개가 느려서 답답했다'   → pacing:slow −      정상 (단, '답답' 덕에 우연히)
```

실패 모드가 "못 배움"이 아니라 **"엉뚱한 원자에 투표함"**이다. `pacing:quality`는 워커가 만드는 후보 feature 어휘와 매칭될 보장이 없어 학습량만 희석시킨다.

부정·이중부정·혼합절 처리(`'설득력이 없는 건 아니다'` → negation_scope abstain, `'문체는 좋지만 캐릭터가 밋밋하다'` → 절 단위 분리)는 정상 동작을 확인했다. 감사문이 P0로 보고한 그 부분 수정은 실제로 됐다.

### P1-7. frozen request의 profile 일치 검사 누락

**[독해]**

`new_entry.py:37`은 `context_id` 일치만 확인하고 draft의 `entry.profile_id`와 `request.profile_id`를 대조하지 않는다. `finalize_entry`가 `entry.profile_id`를 trace 값으로 덮어쓰므로 사후 흔적도 남지 않는다.

실질 피해는 프로필별 prospective 평가 오염이다. A 프로필 모델의 예측이 B 프로필 실적으로 집계된다.

### P2 항목

- **[독해]** `preference-revisions/` 무한 증가. revision당 약 128KB(9 리뷰 기준, `source_files` 전체 포함), 평가마다 1개 생성. 동기화 트리 안에 있어 push마다 전량 재복사된다. 감사문의 "200개 제한"은 `preference-learning-history.json`에만 적용된다(`:526`).
- **[독해]** 에러 삼킴. `daily_local_stage.sh`의 `validate_repo.py … || true`, `select_search_profiles.py:100-104`의 bare `except Exception`. 저장소 자체 규칙 위반.
- **[독해]** `select_search_profiles.main:97`이 `--include-preferences` 없이도 `rebuild_preferences()`를 무조건 호출. 결과를 버리면서 모델/projection 파일을 쓰는 부수효과가 있고 P0-1과 곱해진다.
- **[실행]** 죽은 상수 6개. `MAX_LEARNED_SHARE` `MATURITY_SCALE_EVENTS` `ATOM_PRIOR_STRENGTH` `ATOM_EVENT_BUDGET` `PAIRWISE_CONTEXT_BUDGET` `_feature_rows` 전부 정의만 되고 사용처 0. 실제 값(`4+support`, `.28*maturity`)은 수식에 리터럴로 박혀 있어 튜너블처럼 보이는 게 착시다.
- **[독해]** `_quality_gate:344`의 confirmation이 `rows[:-5]`로 "최근 5개 제외"를 하는데 `rows`는 시간순이 아니라 `context_id` 사전순 정렬(`:315`)이다. entry id가 `YYYY-MM-DD-NN`이라 우연히 맞을 뿐, id 규칙이 바뀌면 조용히 틀린다.
- **[독해]** `project_backend._capture_result_create_only`의 create-only 시맨틱(`open("x")`)과 충돌 검출은 정확하나 `fsync`가 없다. `preference_state.save`는 fsync를 하므로 내구성 규율이 불일치한다.
- **[실행]** `config/automation.json`의 `dedupe.repeat_candidate_cooldown_days: 30`과 `default_mode: "strict_seen_index"`를 읽는 코드가 저장소에 없다. `work_index.py --unseen-only`는 워커가 호출해야 하는 조언용 CLI일 뿐이고 `rank_candidates` 경로는 seen 여부를 보지 않는다. `canonical-pipeline.md` §2는 "consulted before expensive sampling/ranking"이라고 단정한다.

### 문서-구현 불일치

**[실행]**

- `docs/entry-format.md:59-65`의 `preference_features` 예시에 `sample_id` / `start` / `end` / `evidence`가 없다. `preference_contract.features()`는 이들이 없으면 `'feature requires exact sample quotation and sample_id'`로 raise한다. **워커가 이 스펙 문서를 그대로 따르면 랭커가 100% 실패한다.** 워커가 읽는 유일한 포맷 스펙이므로 실행 차단 요인이다.
- `docs/entry-format.md:69` "현재 요청 적합도는 72%, 누적 취향은 28%인 secondary reranker". 실제 구현은 비율 혼합이 아니라 `base_score + bounded additive shift`이며, `preference-harness-audit.md` D절이 스스로 "실제 score를 base와 이 비율로 혼합하지 않는다"고 부정한다.
- `canonical-pipeline.md` §2의 seen-index / 300k floor 서술이 위 P1-2·P2 dedupe 항목과 어긋난다.

---

## 3. 정상 동작을 확인한 것

과잉 지적을 피하기 위해 명시한다. 아래는 **[실행]**으로 정상을 확인했다.

- 84개 테스트 전부 통과, `validate_repo.py` ok
- private 증거 차단: `.gitignore`가 `preference-*.json`, `preference-evidence/`, `preference-revisions/`, `daily-taste-state.json`을 모두 제외하고, `validate_repo.py:35-38`이 `git ls-files workspace`로 추적 여부를 재확인한다
- legacy allowlist 정합: `config/preference-policy.json`의 4개 id가 현존 entry 4개와 정확히 일치하며, 향후 신규 entry는 schema 2 + trace 없이는 `validate_repo` / `register_targets` 양쪽에서 막힌다
- 번역 lane의 create-only 영수증: `open("x")` + 동일성 비교 기반 idempotent 복구, 불일치 시 `LOCAL_RESULT_CONFLICT`
- 과잉반응 억제: 실사용 state에서 atom 11개 전부 tentative, applied score L1 0.170564, gate calibrating ×0.5. 취향 모델이 후보 점수를 흔들지 않는 단계가 맞다
- runtime 미러 현재 동기 상태 정상 (충돌 0)

---

## 4. 2차 점검 결과에 대한 교차검증

별도로 제시된 자체 점검 4건을 재현했다. **3건 확인, 1건 반증.**

| 지적 | 판정 |
|---|---|
| P1 length_exception 계약 충돌 | **확인** (본 문서 P1-1) |
| P2 entry-format.md 구버전 수식 + feature 예시 누락 | **확인.** 단 P2가 아니라 E2E 실행 차단 요인 |
| P2 freeze-request의 profile 일치 검사 누락 | **확인** (본 문서 P1-7) |
| P1/P2 exploration quota 부족 시 shortlist 개수 감소 | **반증. 현재 도달 불가능** |

### exploration 항목 반증 근거

**[실행]** 무작위 4000회 스윕(n 1–20, count 0–20, review_budget 0–20, `minimum_base_score` 0/60/70/80)에서 `len(selected) != min(count, survivors)` 불일치 **0건**.

불변식 때문이다. `floor = max(min_base, cutoff-5)`이고 `cutoff = ordered[count-1].base_score`이므로 항상 `floor ≤ cutoff`다. 그런데 `pool = ordered[count-quota:]`의 앞쪽 `quota`개는 전부 `base ≥ cutoff ≥ floor`다. 따라서 `len(frontier) ≥ quota`가 항상 성립하고 `preference_rank.py:83`의 `quota=min(quota,len(frontier))`는 quota를 줄일 수 없다. `if not quota` 분기가 실제로 타는 경우는 `review_budget < 5` 또는 `count < 5`뿐이다.

**다만 고칠 가치는 있다.** 이 불변식은 코드 어디에도 적혀 있지 않고 테스트도 없다. `floor`에서 `max()`를 빼거나, frontier에서 seen 작품을 제외하는 필터를 나중에 넣거나, `minimum_base_score` 의미를 바꾸면 조용히 깨진다.

수정 시 주의: `exploit`을 단순히 `ordered[:count-quota_new]`로 다시 자르면 explore 당첨 후보와 겹친다. explore를 frontier에서 먼저 뽑고, exploit은 `ordered`에서 explore 키를 제외하며 앞에서부터 `count - len(explore)`개 채우는 형태여야 한다.

### 테스트 공백 (확인)

- `test_explore_reaches_review_budget_and_abstains_from_garbage`가 `count=10`을 쓰지만 헬퍼의 `review_budget=5`(`tests/test_preference_harness.py:34`) 때문에 `min(10,5)=5 → quota=1`로 눌린다. **quota 2 경로는 한 번도 돌지 않는다.**
- `length_exception` 문자열이 `test_preference_harness.py` / `test_preference_feedback.py` / `test_preference_entry.py` 어디에도 없다.

---

## 5. cohort 제약과 수정 순서

**이 문서에서 가장 실무적인 항목이다.**

P0-2 때문에 수정 목록을 두 갈래로 갈라야 한다. `code_revision()`이 보는 6개 파일을 건드리면 그때까지 쌓인 prospective 데이터가 폐기되기 때문이다.

**E2E 이전에 반드시 끝내야 하는 것** (`scripts/preference*.py`를 건드림):

- P1-1 length_exception 계약 + P1-2 min_chars fail-open — `preference_contract.py`
- exploration 불변식 명시화 + 테스트 — `preference_rank.py`
- P0-1 rebuild 성능 — `preference_feedback.py`
- P1-6 원자화기 활용형 — `preference_atoms.py`

**나중에 해도 무해한 것** (glob 밖):

- P1-7 `new_entry.py` profile 검사
- P1-3 search-profiles 락 경합
- P1-4 runtime_sync 충돌 해소 경로
- P2 전반

**단, `docs/entry-format.md`는 glob 밖이지만 E2E 자체를 막으므로 선행 조건이다.**

P0-1을 "나중에"로 미루는 게 특히 위험하다. 9 리뷰인 지금은 보이지 않지만, prospective 데이터가 쌓이기 시작하는 바로 그 구간에서 비용이 터진다. 그때 고치면 그동안 모은 cohort를 함께 버리게 된다.

20 contexts를 채우려면 하루 1엔트리 기준 최소 20일간 `preference*.py`를 한 줄도 건드릴 수 없다는 뜻이므로, 그 전에 전부 털고 들어가는 편이 낫다.

---

## 6. 권장 조치 순서

1. `docs/entry-format.md` feature 예시와 72/28 서술 수정 — E2E 선행 조건
2. length_exception 계약 + min_chars 기본 하한을 `validate_request`/`eligibility`에서 함께 정리
3. exploration 불변식 테스트 고정 (quota 2→1 축소 케이스 포함)
4. rebuild 증분화 + `model_snapshot` 포인터화
5. 원자화기 활용형 미스 시 generic 폴백 대신 `unresolved` abstain
6. 회귀 테스트 3종 추가: quota 축소 / 길이 예외 레인(정직한 fail 기록 포함) / min_chars 미선언 fail-open
7. **여기까지 끝낸 뒤** schema-2 entry 1건을 freeze → discovery → sample → rank → trace → finalize → register → review까지 통으로 실행
8. 통과 확인 후 커밋
9. 이후: `new_entry.py` profile 검사, search-profiles 락 통일, runtime_sync 부분 import + 해소 명령, cohort id 정책

7단계 이후 쌓이는 평가가 비로소 실제 prospective 검증 데이터가 된다.

---

## 7. 검증하지 못한 것

- **[미검증]** 워커가 실제 본문 의미를 올바르게 feature로 분류하는지. 계약은 해시와 인용 offset만 증명하며 의미 정확성은 증명하지 않는다.
- **[미검증]** 다음 실제 웹 탐색의 recall 변화. 독립 사용자 label 없이는 unit test로 대체 불가하다.
- **[미검증]** GitHub Pages 실배포 및 Tailnet 경유 동작.
- **[미검증]** 번역 lane의 E2E 재실행. 기존 테스트(`test_project_backend.py`, `test_project_translation_integration.py`) 통과에 의존했고 브라우저 런너를 실제로 돌리지는 않았다.
- **[독해]**로 표시한 항목은 코드 경로 추적으로 판단했으며 실패를 실행으로 재현하지는 않았다.

---

## 8. 문서 갱신 범위

이 문서는 검토 결과만 기록한다. `docs/TASKS.md` / `docs/PROJECT_STATUS.md`는 갱신하지 않았다. 위 조치 항목은 아직 채택 여부가 결정되지 않은 제안이며, 결정 전에 작업 추적 문서에 완료 예정 과제로 올리면 실제 상태를 잘못 표시하게 되기 때문이다. 채택이 결정되면 6절 목록을 `TASKS.md`로 옮기는 것이 맞다.
