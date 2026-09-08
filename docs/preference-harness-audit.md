# Fieldnotes 독립 감사 및 순차 수정 검증 — 2026-09-08

후속 검수: [Claude 리뷰 교차검수·수정 결과](pipeline-harness-review-verification.md)가 이후 확인된 결함, 95-test 검증, 10-review migration과 현재 계약을 기록한다. 아래 원 감사의 시점별 수치를 현재 수치로 오인하지 않는다.

대상: canonical working tree와 private runtime. 설계 문서는 구현의 증거로 취급하지 않았다. 최초 감사의 실패를 재현한 뒤 사용자의 순차 수정 지시에 따라 수정·시험·runtime migration을 수행했다. 이 보고서는 최초 실패와 수정 후 상태를 구별한다. 실제 사용자의 메모/샘플은 이 문서에 복사하지 않았다.

## A. Verdict

**NEEDS REVISION — 실제 검색품질의 지속 개선이라는 최종 기준.**

최초 구현은 FAIL이었다. 학습 방향, 수정 중복, trace 변경, request override, pair gate 증폭에서 실패가 재현됐다.
수정 후 구현 방어선은 테스트와 runtime에서 검증했지만 실제 prospective context는 아직 0개다.
따라서 “매일 평가할수록 실제 검색이 좋아진다”는 PASS를 내릴 증거는 없다.
추가 프레임워크보다 새 탐색의 frozen trace와 독립 사용자 평가를 모으는 것이 다음 검증 단계다.

## B. Pipeline Map

| 단계 | 실제 파일/함수 | 실행 경계 |
|---|---|---|
| Discovery 요청 | `select_search_profiles.choose/main` → `new_entry.main --freeze-request` | 기본 출력은 request-only. 이전 누적 취향을 base score로 우회 전달하지 않음 |
| 후보 수집/중복 | discovery worker → `rebuild_work_index.canonical/rebuild` → `work_index.annotate` | 웹 검색과 작품 의미 판단은 worker 수행. 후보 recall을 보증하는 자동 검색 엔진은 아님 |
| Sampling | worker가 본문 저장 → `preference_contract.verify_samples` | 본문 hash·인용 offset 검증; 내용 해석의 정확성까지 자동 증명하지 않음 |
| Ranking | `preference_rank.rank_candidates/score_candidate` → `persist_trace` | hard-filter receipt, base floor, explicit dimension mask, bounded score, frontier explore |
| Entry / 읽기 | `preference_contract.finalize_entry` → `validate_repo` → `register_targets` → acquisition/translation worker | 선택 순서 고정; explore를 실제 리뷰 예산 안에 배치 |
| Review | `taste.js` / `console.js` → `private_console.save_taste_response` / `/api/feedback` → `preference_feedback.record` | 동일 context/work/scope는 하나의 리뷰, UI 전환은 revision |
| Learning | `_journal` → `_effective_events` → `analyze_note` → `_aggregate` → `rebuild` | raw operation replay, derived model/projection 분리, 단일 리뷰 L1 step 제한 |
| Evaluation | `_prospective_rank_metrics` → `_quality_gate`; `preference_evaluate.evaluate` | frozen prediction/user reward만 사용; context 평균, coverage/recall benchmark 구별 |
| Next Discovery | 다음 `select_search_profiles.main`/`preference_rank.main`에서 rebuild | 새 추천에서 모델 revision·샘플·점수·확률을 다시 고정 |

이 흐름은 CLI와 worker 계약으로 연결된다. 새 complete entry 및 target 등록에 trace 검사를 추가해 누락된 rerank 단계가 정상 완료로 통과하지 못하게 했다. 외부 daily worker의 다음 실제 웹 탐색을 이번 시험에서 대신 수행하거나 성공했다고 주장하지 않는다.

## C. Critical Findings

아래 P0/P1은 최초 구현의 실패다. 파일 링크는 수정된 함수의 현재 위치이며 원본 소스 line이라고 주장하지 않는다. 최초 재현 JSON/스크립트는 private 감사 증거에 보존했다.

| Severity | Finding | Evidence | Impact | Fix / 현재 상태 |
|---|---|---|---|---|
| P0 | 부정 scope 및 품질 결손의 학습 방향 오류 | `preference_atoms.analyze_note`와 `test_negative_scope_and_mixed_clauses`, `test_quality_deficit_cannot_penalize_positive_trait` | 빠른 전개 불호를 호로 저장; 설득력 부족 불호가 설득력 감점으로 연결 | 절 단위 scope, 이중부정 abstain, deficit atom 분리, raw 재추출 완료 |
| P0 | Daily/Console의 같은 평가가 서로 다른 event로 누적; 동시 쓰기 손실 가능 | `preference_feedback.record/_journal`, `preference_state.state_lock/save`; 실제 HTTP 교차 수정 시험 | 별점 수정 후 과거 reward 잔존, 평가 소실 | context/work/scope identity, operation journal, flock/atomic replace; 20 concurrent 및 retry 검증 |
| P1 | trace overwrite 및 평가 후 생성한 정보의 과거 소급 | `preference_rank.persist_trace`, `preference_contract.prospective_trace` | hindsight를 prospective로 오인, pair feature 누수 | create-only hash, pre-review creation time, frozen model/source, code cohort 검사 |
| P1 | 한 entry의 수십 pair가 gate를 승격; tie 비교 population 차이 | `_pairwise_atom_model`, `_prospective_rank_metrics`, `_quality_gate` | 최초 40 pair 단일 context가 g=1 도달; 잘못된 검증 확신 | pair/context 정규화, 동일 pair population/tie .5; 20 contexts/60 pairs+5 confirmation |
| P1 | 현재 요청 위반 후보·충돌 취향을 차단하지 못함 | `preference_contract.eligibility/protected_dimensions`, `preference_rank.score_candidate` | 느린 정치극 명시에도 빠른 전개 취향이 역전 유발 | fail-closed receipt와 explicit dimension mask, 새 request freeze |
| P1 | duplicate features가 단일 review 효과를 증폭; maturity/gate 전체 변경 bound 없음 | `features`, `preference_feedback.rebuild`, `score_candidate` | 최대 rerank shift까지 반복 feature 가산 | feature 중복 거부, 전체 vector L1≤4, 리뷰별 변화≤.5 |
| P1 | ranking trace private sync/ignore 경로 누락 | `runtime_sync.PRIVATE_STATE_FILES/MUTABLE_WORKSPACE_DIRS`, `.gitignore`, `validate_repo` | refresh 시 기록 손실, public artifact 노출 위험 | trace/evidence/revisions 포함, 양쪽 lock와 conflict 거부, GET/HEAD 404 확인 |
| P1 | 추천 품질 향상의 실제 근거 부재 | live migration: 사용자 9 reviews, historical 14 pairs, prospective 0 | observed 만족도만으로 자기강화 시스템을 개선 모델로 오인 | 과거 backfill 금지; calibrating 유지. 실제 품질 검증은 **미완료** |
| P2 | closed vocabulary와 샘플 해석의 불확실성 | `analyze_note`, `verify_samples` | 새 표현을 배우지 못하거나 worker feature가 부정확할 수 있음 | unresolved UI/원문 유지, 새로운 candidate feature 허용. 모든 의미 정확성은 미보장 |
| P2 | selected-only reward / candidate recall 부재 | `preference_evaluate.evaluate` 현재 benchmark unavailable | reranking 개선이 discovery 개선처럼 보임 | coverage/0-propensity/독립 user recall@20 분리; 실제 label 수집 필요 |
| P2 | 승인된 보조 신호가 반복 제안되거나 hard prior로 오인 | `rebuild`, `_apply_suggestion`, `select_search_profiles.main` | 같은 제안 반복·묵시적 필터 우회 | 승인 제안 억제; 승인 기록도 자동 discovery hard filter로 전달하지 않음 |
| P3 | immutable source/evidence archive 용량 | `rebuild` revision recipe | 장기 저장량 증가 | 요약 history 200개 제한. 원증거의 자동 삭제는 하지 않으며 보존 정책 추후 필요 |

## D. Overreaction Audit

수정된 함수를 별도 임시 state에서 직접 실행했다. 서로 다른 작품/entry에서 동일한 atom 1개를 지속적으로 긍정한 경우다. 사건 간 몇 초의 90일 decay 때문에 반올림 전 아주 작은 차이가 있다.

`D=부호 있는 support`, `S=atom support`, `E=전체 유효 review support`.

- `effective_weight=D/(4+E)`, `confidence=|D|/(4+S)`.
- `m=1-exp(-n/12)`, `g=.5` (prospective 미확인), `target L1≤4mg`.
- 현재 vector는 raw review revision마다 target 방향으로 L1 최대 .5만 이동한다.
- 아래 share는 호환용 diagnostic `.28*m*g`다. 실제 score를 base와 이 비율로 혼합하지 않는다.

| 평가/독립 context | effective weight | confidence | raw maturity | gate 후 maturity | diagnostic share | candidate shift | stage |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | .2000 | .2000 | .0800 | .0400 | .0112 | .0320 | tentative |
| 3 | .4286 | .4286 | .2212 | .1106 | .0310 | .1896 | reinforced |
| 5 | .5556 | .5556 | .3408 | .1704 | .0477 | .3786 | stable |
| 10 | .7143 | .7143 | .5654 | .2827 | .0792 | .8077 | stable |
| 20 | .8333 | .8333 | .8111 | .4056 | .1136 | 1.3519 | stable |
| 50 | .9259 | .9259 | .9845 | .4922 | .1378 | 1.8231 | stable |
| 100 | .9615 | .9615 | .9998 | .4999 | .1400 | 1.9226 | stable |

한 리뷰의 atom 수 1/2/5/10/20 모두 총 support=1, 총 effective weight=.2, 첫 target=.0319822341로 동일하다. pair는 10작품, 5등급의 중복 rating 때문에 최대 45 중 실제 40 unequal pairs가 만들어지는 시험을 사용했다. 같은 pair 10배 복제에도 weight가 변하지 않았다.

고정 candidate feature/request에서 한 review는 점수 최대 .5, 후보 두 개의 점수차 최대 1.0을 변경한다. **순위 번호의 상한은 없다.** 100개 후보가 .01점 안에 모여 있으면 작은 변경으로도 100위 이동이 가능하다. 첫 평가의 대칭 feature 역전 가능 base gap은 약 .064점이다. “순위 최대 1칸”은 구현하지 않았고 보증하지 않는다. exploration의 의도적 위치 변경과 rerank score 변화도 별개다.

20회는 첫 평가보다 약 42배 강하지만 미검증 모델의 목표는 ±2점 이하라 큰 request-fit 차이를 쉽게 뒤집지 않는다. gate 하향 후 이미 적용된 vector는 .5/revision 제한으로 감속하므로 즉시 zero가 되는 것은 아니다. 코드/config migration은 review update와 구별한다.

## E. Continuous Learning Audit

수정 후 상태의 점수다. 코드 방어와 실사용 효과는 별도로 감점했다.

| 기준 | 점수 / 5 | 근거 |
|---|---:|---|
| single-feedback robustness | 5 | 전체 vector 변화 bound와 long memo/dedup 검증 |
| cumulative learning | 4 | 1→100 시뮬레이션 강화; 실제 유용성 미측정 |
| contradictory evidence handling | 4 | 10+/10− mixed·near-zero, 90일 decay; 제한된 의미 해석 |
| pairwise stability | 4 | context budget, shared measured features; context 간 작품 상관은 남음 |
| exploration quality | 3 | frontier/확률/review 도달; discovery recall 미증명 |
| current-request protection | 4 | 기계 계약과 mask; semantic receipt는 worker 정확성에 의존 |
| idempotency | 5 | 교차 UI/재전송/concurrent/rebuild 확인 |
| calibration | 3 | 문턱·bootstrap·감속 검증; 임계값 실측 calibration 부족 |
| prospective evaluation | 3 | 고정 예측 경로 검증, 실제 표본 0 |
| observability | 4 | revision/coverage/unresolved; 장기 운영 관측 필요 |
| recovery/rebuild | 5 | 실제 9개 모델 삭제 후 byte-identical rebuild |
| privacy/runtime integrity | 4 | private sync/충돌/API 차단; 외부 GitHub 배포 실증은 이번 범위 아님 |
| **합계** | **48 / 60** | 품질 PASS 점수가 아님 |

## F. Search Quality Harness Assessment

| 질문 | 판정 | 경계 |
|---|---|---|
| 1. 평가를 쌓을수록 실제 품질을 측정할 수 있는가? | PARTIAL | 선택 후보 prospective 지표 가능; recall 독립 label 필요 |
| 2. 품질 저하를 자동 감속하는가? | YES | synthetic 34 bad contexts에서 g=.125; 실제 저하 데이터는 아직 없음 |
| 3. 1회 이상치에 강한가? | YES | 점수 변화 bound, 순위 번호 bound는 아님 |
| 4. 반복 선호가 강화되는가? | YES | 독립 context 1/3/5/10/20/50/100 실행 |
| 5. 상충 신호가 약화되는가? | YES | 부호 상쇄·mixed·새 반대 evidence 반영 |
| 6. 새 취향 영역을 계속 탐색하는가? | PARTIAL | 관측 pool frontier만; 검색되지 않은 공간은 보증 불가 |
| 7. 현재 요청이 항상 우선하는가? | PARTIAL | 선언된 hard filter/차원은 강제; 자연어 누락 판단은 worker 의존 |
| 8. prospective validation을 하는가? | YES | frozen pre-review trace, current code cohort; 현재 실제 pair=0 |
| 9. 검색 당시 상태를 재현하는가? | PARTIAL | 모델/후보/본문/점수/seed 재현; 당시 전체 웹 검색환경은 불가 |
| 10. raw feedback만으로 재구축하는가? | PARTIAL | 직접 메모 모델 가능; pair 포함 완전 재구축에는 raw trace·config·code도 필요 |

## G. Recommended Harness vNext

최소 변경안 1–4는 이번 수정에 반영했다. 5는 관측 도구까지 구현했으며 실사용 데이터가 남았다.

| 변경 | 문제 | 변경식/알고리즘 | 기대효과 | regression risk | 필요한 테스트 |
|---|---|---|---|---|---|
| 1. shared review journal | 두 UI 중복·수정·손실 | identity(context,work,scope), flock, atomic save, raw revision replay | 동일 평가 한 번만 학습 | 기존 날짜/entry migration 오류 | 교차 HTTP, retry, concurrent, 원문 보존, 삭제 rebuild |
| 2. atom budget와 방향 | 길이 증폭·부정 오류 | 1/k support, D/(4+E), deficit 분리, abstain | 단일 이상치 억제 | closed vocab 미학습 증가 | 의미 공격, 20 atom, 10+/10−, 새 표현 unresolved |
| 3. request와 immutable trace | hindsight/request 우회 | receipt+sample hashes+explicit mask+frozen slate | label leakage 차단 | legacy 호환·worker fail-closed 빈 결과 | MUST NOT/장르/느린 정치극, hash 변조, entry 순서 변경 |
| 4. context gate와 점진적 weight | pair explosion·급격한 gate jump | context means, bootstrap, 20/60+5, L1 delta≤.5 | correlated 판단 과대계산 억제 | 감속 반응 지연·small sample bootstrap 오차 | 40pair/1context, 34good/bad contexts, model cohort 변경 |
| 5. recall와 품질 관측 | 추천 pool 밖은 blind spot | 독립 user label benchmark, recall@20, selected/reviewed/explore coverage | discovery와 ranking 효과 분리 | benchmark 취향/시간 drift·평가 피로 | user label source 거부 규칙, 독립 holdout 10 intents 이상 |

ML framework 추가는 필요 없다. 20% exploration은 현재 5편 리뷰 예산에서 1편이라 운영하기 쉬운 시작값이며 최적값이라고 검증되지 않았다. 충분한 데이터 전 자동 증량은 하지 않는다. 추후 20 context 단위로 explore의 실제 읽힘/고평점/recall 기여를 본 뒤 10–20% 범위에서 조절할 수 있다.

## H. Exact Acceptance Criteria

| 기준 | 수치 | 현재 결과 |
|---|---|---|
| 단일 최초 review | 동일 feature 후보 shift≤.1/100 | .031982 통과 |
| 임의 review 수정 | 고정 feature/request score delta≤.5 | L1 projection 및 correction 회귀 통과 |
| 총 influence ceiling | 미검증 target≤2, 검증≤4/100 | 구현·시험 통과; 감속 적용은 .5 step |
| 긴 메모 | 1/2/5/10/20 atom 총 target 편차≤1e−10 | 통과 |
| stable 최소 독립성 | ≥5 works, ≥5 contexts, support≥3, consistency≥.8 | 구현; 현재 11 atom 모두 tentative |
| conflict | 10+/10− effective abs<.05 및 mixed | 통과 |
| pair dependency | 동일 pair 10배 복제 weight 동일, 1context 40pair로 g>.5 금지 | 통과 |
| prospective gate 시작 | ≥20 contexts 및 ≥60 common pairs | 현재 실제 0/0으로 calibrating |
| model promotion | delta≥.05, bootstrap lower90>0, 추가5contexts confirmation | synthetic 통과, 실사용 대기 |
| 단계적 promotion | 25contexts g=.55, context당+.05, ≤1 | synthetic 34contexts g=1 |
| degradation | ≥10contexts delta≤−.05 g=.25; ≤−.10 g=.125 | synthetic 통과 |
| exploration | 리뷰예산5에 적격 explore1; base≥60, cutoff−5 이내 | 통과; 실측 비율/효과 대기 |
| trace | 모든 새 complete entry에 immutable hash, request/선택순서 일치 | validator/integration 통과 |
| 실제 검색품질 PASS | ≥10 독립 search intents의 user recall@20; 이후 분리된 ≥20 prospective contexts/≥60pairs에서 delta≥.05·lower90>0, recall@20 감소≤.02 | 아직 수집 전 |

마지막 기준은 효과 검증 제안이다. 현 데이터로 달성한 숫자처럼 표시하지 않는다. 사용자가 읽지 않은 작품의 reward를 모델로 채워 넣지 않는다.

## I. Final Top 5

1. **후보·본문·요청·점수를 추천 전에 고정하고 완료 경로에서 강제** — 예상 효과: 누수 차단과 실제 품질 측정의 전제 / 구현 난이도: 중 / 우선순위: P1 / 반영 완료.
2. **두 UI 리뷰를 단일 journal로 합치고 수정·재전송·동시 쓰기 보장** — 예상 효과: reward 오염과 데이터 손실 제거 / 구현 난이도: 중 / 우선순위: P0 / 반영 완료.
3. **atom 방향 및 단일 review 전체 영향 budget 수정** — 예상 효과: 초기 취향 오학습·장문 증폭 억제 / 구현 난이도: 중 / 우선순위: P0 / 반영 완료.
4. **pair를 context로 정규화하고 quality gate를 점진적으로 적용** — 예상 효과: 한 entry가 품질 확신을 독점하는 현상 제거 / 구현 난이도: 중 / 우선순위: P1 / 반영 완료.
5. **explore를 실제 읽기 목록에 전달하고 recall·prospective를 분리 관측** — 예상 효과: 자기강화 사각지대 발견과 discovery 개선 근거 확보 / 구현 난이도: 중 / 우선순위: P1 / 도구 반영, 실사용 증거 수집 대기.

## 실행 증거와 테스트 스위트 평가

최종 `/usr/bin/python3 -m unittest discover -s tests`: **84 tests OK**. `validate_repo.py`: ok. `node --check console.js`, `node --check taste.js`, `git diff --check`: 통과. 기존 translation prompt 테스트의 stale expected 문자열 1개는 실제 driver transport receipt 계약에 맞췄다.

새 회귀는 기존 구현과 동일 수식을 베끼는 것에 그치지 않고 예산 불변성, 수정 전후 identity, 변조 거부, 코드 cohort, 34개 good/bad context, raw-only direct replay, 공개 entry projection을 공격한다. 다만 worker가 실제 본문 의미를 바르게 분류하는지와 다음 daily 검색의 recall 변화는 unit test로 검증하지 못한다. 새 표현 semantic corpus와 장기 candidate-set shift holdout은 계속 추가해야 한다.

실제 서버 HTTP: Daily 5점→Console 1점 수정 뒤 단일 event, Daily 표시 exclude, retry 전후 count 1, API 모델 event_count 1. 이 쓰기 시험은 임시 서버/임시 데이터에서 수행했으며 실사용 리뷰를 조작하지 않았다.

실사용 migration: 9 events→9 operations/9 current events, 메모·verdict·태그 보존, derived model 삭제 후 byte-identical rebuild, atom11 모두 tentative, historical pair14/prospective pair0, effective contexts≈2, raw maturity .153514, gate후 .076757, 적용 L1 budget .170564. 기존 launchd runtime 서버 재시작 후 `/api/state`와 `/api/taste/today` 200, private JSON GET/HEAD 404, 핵심 code/state/UI 12파일 canonical/runtime hash 일치 확인.

private 실행 로그·baseline 재현·수치 JSON·migration receipt는 canonical의 ignored `.tmp/preference-harness-v2/`에 보존한다. 원본 state backup은 저장소 밖 `~/.codex/private-backups/`에 보존한다. 이 경로는 공개 배포 대상이 아니다. 기존 미커밋 변경과 이번 수정은 working tree에 남겨 검토 가능하게 했으며 commit/push하지 않았다.
