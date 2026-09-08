# Claude 파이프라인 리뷰 교차검수·수정 결과

검수일: 2026-09-08. 대상은 `docs/pipeline-harness-review.md`와 현재 canonical working tree다. 원본 리뷰는 수정하지 않았다. 코드 독해뿐 아니라 실패 재현, 수정 후 회귀 테스트, private runtime migration을 수행했다.

## 결론

**핵심 지적은 맞았다.** 특히 동기 전체 replay 비용, 코드 파일 해시와 평가 cohort의 결합, 길이 예외의 거짓 pass 요구, 300k 하한 누락, profile writer 경합, 활용형 오분류는 확인 후 수정했다.

다만 리뷰의 모든 설명/제안을 그대로 채택하지 않았다. 기존 length exception의 자동 삭제 주장은 틀리고, profile mismatch가 바로 “A 모델 예측을 B 실적에 집계”한다는 설명은 CLI가 강제하는 profile 일치를 빠뜨렸다. sync의 all-or-nothing 중단 자체는 데이터 일관성을 지키므로 유지했다. 실제 품질 개선이 아직 입증되지 않았다는 판정은 유지한다.

## 항목별 판정과 조치

| 리뷰 항목 | 검수 판정 | 직접 확인한 근거 | 수정 / 판단 |
|---|---|---|---|
| P0-1 동기 rebuild의 초선형 비용 | **확인** | 동일 fixture의 40건 1.772s, 80건 7.315s. 각 operation prefix에서 전체 aggregate 반복 | [rebuild](../scripts/preference_feedback.py#L463): digest 검증된 checkpoint의 신규 revision만 처리. trace 한 번 load/validate. 삭제/변조/의존성 변경 시 full replay |
| P0-1 trace 내 full model/중복 source | **확인** | trace가 model_snapshot 전체를 저장; archive가 동일 source를 반복 저장 | [recipe](../scripts/preference_feedback.py#L444): source/config/operation을 content address로 한 번 저장. trace는 model_ref+revision+code/cohort 참조. HTTP 비동기화는 현재 응답 속도 실측상 필요 없어 도입하지 않음 |
| P0-2 code_revision에 의해 전부 무효화 | **확인, 표현 일부 과장** | 코드 hash 차이만으로 prospective pair 제외. “20일 이상 동결해야만 한다”는 말은 하루 context 수와 개발 빈도 가정 | [SCORING_COHORT_ID](../scripts/preference_state.py#L14) 분리. 동일 scoring 의미의 source 변경은 증거 유지. incompatible cohort는 gate에서 분리하되 cohort_pair_counts로 보존·표시 |
| P1-1 honest length exception 거부 | **확인** | 수정 전 min_chars=fail + fit=pass는 missing_or_failed_check:min_chars로 거부 | [eligibility](../scripts/preference_contract.py#L77): 기본 길이 예외는 정직한 fail receipt와 출처 있는 fit pass로 통과; false pass는 거부 |
| P1-2 min_chars 생략 시 fail-open | **확인** | 수정 전 12,000자가 통과 | 생략/None은 300,000으로 검사; known length와 minimum receipt 필수. scaffold/template도 300000. 명시적 별도 최소값을 기본 예외로 우회하지 못함 |
| P1-3 profile writer 락 3종 | **확인** | Console/selection/plain write와 approval의 lock 규율 불일치 | [save_profiles/update_selection](../scripts/private_console.py#L56), selector 모두 공통 lock+atomic save. 단순 락만으로 stale 브라우저 body는 막지 못하므로 config revision CAS도 추가 |
| P1-4 sync all-or-nothing / resolver 없음 | **부분 확인** | 독립 archive 추가도 tree divergence; 명시적 해결 CLI 없음. 전체 중단은 coupled raw/model 일관성 보장 기능 | immutable trees는 union, 동일 경로 다른 내용은 conflict. mutable state 부분 import는 채택하지 않음. [resolve](../scripts/runtime_sync.py#L331)는 exact path·양쪽 expected hash·사전 양쪽 backup 요구 |
| P1-5 finalize가 LENGTH EXCEPTION 삭제 | **버킷 불일치는 확인, 작품 삭제 주장은 반증** | 이전 finalize는 선택된 예외도 shortlist에 넣고 별도 버킷만 비움. legacy entry를 자동 finalize/migrate하는 호출도 없음 | 예외 버킷을 유지하고 selected_candidates가 양쪽을 frozen preference_rank 순서로 병합. registration과 Daily deck 순서 보존 시험 |
| P1-6 한국어 활용형의 잘못된 fallback | **확인** | 빨라서 좋았다→pacing:quality, 빨랐다→없음, 잘 읽힌다→prose:quality 재현 | atomizer 2.2: 빨라/빨랐·느려/느렸·읽힌/읽혔. generic assessment만 fallback, 미등록 구체 표현은 unresolved |
| P1-7 freeze profile 검사 누락 | **누락 확인, 영향 설명은 부분 반증** | draft A/request B가 freeze 가능. 하지만 rank CLI는 --profile과 request/trace profile 일치 강제 | freeze에서 draft/request 일치, trace commit과 finalize에서도 profile 확인. A 예측이 자동 B 모델로 둔갑한다는 단정은 하지 않음 |
| P2 revision archive 성장 | **확인** | 200개 제한은 history 요약에만 해당 | 반복 source/operation 객체 dedup, unchanged immutable file 재복사 생략. 영구 archive의 무제한 총성장은 여전히 보존 정책 대상 |
| P2 에러 삼킴 | **확인** | validate_repo 실패를 || true, operational lesson 실패를 빈 배열로 은폐 | local-stage 실패 기록/비정상 종료; lesson read 실패 전파 |
| P2 request-only에서 rebuild 실행 | **확인** | include flag와 무관한 호출 | 기본 selector에서는 rebuild하지 않음. mock call-count=0 및 preference 필드 제외 시험 |
| P2 죽은 상수/alias | **확인** | 수식 literal을 제어하지 않는 선언 | 사용하지 않는 해당 상수/alias/PREFERENCE_MODEL 선언 제거. 가짜 튜닝 지점 유지하지 않음 |
| P2 confirmation rows 사전순 | **확인** | 최근5개 제외가 id 사전순 | 실제 trace created_at 순서로 정렬. z-older/a-newer 반례 시험 |
| P2 translation receipt fsync 누락 | **확인** | flush 후 close만 수행 | 기존 create-only 의미 유지하면서 file fsync 추가. 전원 차단 실험까지 수행한 것은 아님 |
| P2 dedupe 설정 미강제 | **확인** | rank 경로가 index를 읽지 않았음 | [dedupe_context](../scripts/preference_rank.py#L54): strict_seen_index/cooldown 30일 실제 적용, index 없으면 거부. 명시적 revisit 요청+출처 receipt만 예외. 최초 취득 전 worker 호출까지 랭커가 소급 보증하지 않음 |
| 문서 feature sample 필드/72·28 | **확인** | 예시 그대로는 검증 불가; 실제 additive 수식과 다름 | entry-format 예시를 hash/source/span/receipt 포함으로 교체. bounded additive 명시, 현재 CLI와 두 버킷 순서 설명 |
| exploration quota 부족 반증 | **현재 구현에서는 결론 동의, 논증 보완** | nonzero learned weights 및 quota=2를 포함한 추가 100개 pool 실행에서 개수/중복/slot 위반 없음 | pool 앞 quota개가 반드시 base≥cutoff라는 설명은 성립하지 않을 수 있음. 대신 전체에서 base≥cutoff가 count개 이상이고 exploit이 count−quota개이므로 frontier에 ≥quota개 남는 개수 논증이 정확. 미래 필터 변경도 안전하도록 explore를 제외한 exploit refill |

## 성능: 응답 경로와 복구 경로를 구분

새 성능 시험은 context당 5개 서로 다른 작품을 사용했다. 표의 correction은 기존 평가 1개를 실제 `record()`로 수정하여 JSON commit/모델 생성/recipe 저장까지 수행한 시간이다. 같은 머신의 단일 측정이므로 서비스 p95라고 주장하지 않는다.

| 누적 평가 | 모델 삭제 후 full replay | checkpoint 기반 수정 1건 |
|---:|---:|---:|
| 40 | .621s | .065s |
| 80 | 1.434s | .064s |
| 160 | 4.841s | .111s |
| 320 | 18.645s | .230s |
| 640 | 75.983s | .447s |

**일반 리뷰 저장마다 이력 전체를 replay하던 문제는 해결했다. 전체 복구 비용이 선형이 됐다는 뜻은 아니다.** source/config/관련 과거 trace의 변경 또는 checkpoint 손실은 full replay를 유발한다. 많은 데이터가 쌓인 뒤 코드 배포는 UI 요청 전에 CLI rebuild로 준비해야 한다. 640건 복구의 약 76초는 알려진 한계다. 비동기 작업 큐나 ML framework를 추가하지 않았다.

checkpoint는 operation prefix hash, profiles hash, code_revision, 기존 operation이 참조하는 trace hash와 자신의 전체 content hash를 검증한다. 위조·불일치 checkpoint는 적용하지 않는다. correction 후 incremental 결과와 삭제 후 replay 결과가 완전히 같은지 시험했다. 단일 review coefficient L1≤.5 방어는 유지한다.

모델 archive는 기존 원본을 삭제하지 않고 새 recipe만 compact 형식으로 쓴다. source/config/각 raw operation은 중복 저장하지 않지만 recipe의 operation-reference 목록과 영구 evidence 총량은 계속 자란다. “archive 무한 증가가 완전히 해결됐다”는 주장은 하지 않는다.

## 검증 범위

- `/usr/bin/python3 -m unittest discover -s tests`: **95 tests OK**. 이전 84개와 새 11개 검수 회귀다. import된 테스트 클래스를 중복 실행해 숫자를 늘리지 않았다.
- `validate_repo.py`: ok; `node --check console.js`, `node --check taste.js`, `zsh -n scripts/daily_local_stage.sh`, `git diff --check`: 통과.
- 새 회귀: 기본 최소값/정직한 예외/명시값 보호, 활용형과 abstain, checkpoint 일치와 변조, cohort 보존과 분리, 시간순 confirmation, quota=2, seen-before-sample/cooldown, stale profile CAS, request-only 무부작용, immutable union/backup/CAS resolver, schema2 CLI 통합.
- schema2 통합: 임시 root에서 scaffold → 잘못된 profile freeze 거부 → freeze → sampled rank → immutable trace/recipe → finalize → 예외 버킷/전체 순서 검증 → top5 registration → synthetic 두 평가 → prospective pair=1 → validator. 원본 웹 discovery나 번역 브라우저 실행을 대신한 시험이 아니다.
- 임시 HTTP 서버: Daily 5점→Console 1점 교차 수정은 현재 event 1건, Daily exclude 표시, retry 전후 count 1 유지. 실제 사용자 평가를 이 시험에 쓰지 않았다.

## 실제 runtime 적용

작업 중 runtime에 새 평가가 추가되어 canonical 9건/runtime 10건이었다. 서버를 잠시 중지하고 양쪽 private state를 저장소 밖에 백업한 뒤 runtime 변화 5파일과 immutable 파일을 먼저 가져왔다. **10 raw operations 및 평가 10건의 별점·메모·태그·scope/context를 그대로 보존**했다.

모델 migration 약 .313s, 삭제 후 full rebuild 완전 일치. 현재 atom 11개 전부 tentative, applied L1≈.169809, prospective pair 0이다. 실사용 trace를 합성 데이터로 채우지 않았다.

기존 launchd service를 같은 주소/설정으로 재시작했다. `/api/state`, `/api/taste/today` 200, profile revision 제공, private JSON GET/HEAD 404, code/state/UI 핵심 10파일 canonical/runtime 일치. 이전부터 열어 둔 콘솔이 stale revision 오류를 보이면 새로고침 후 사용한다.

## 남은 한계와 판정

실제 사용자 prospective data는 여전히 0이다. 이번 수정은 방어 계약·일반 저장 성능·증거 연속성 개선이며 실제 검색품질 상승을 증명하지 않는다. 새 사용자가 아니라 기존 한 사용자의 독립 context/recall 관측을 계속 모아야 한다. 의미 분류 정확성, 실제 웹 candidate recall, Tailnet/GitHub Pages 배포, 번역 브라우저 E2E는 이번 교차검수의 실증 범위가 아니다.

실행 원본은 private ignored `.tmp/claude-review-verification/`에 남겼다. 최초 리뷰 파일은 보존했고, 기존 미커밋 변경과 이번 수정은 working tree에서 검토할 수 있도록 commit/push하지 않았다.
