# Preference Learning v0.1

## Daily Taste review

`taste.html`은 매일 피드백의 기본 화면이다. 선택 날짜의 `shortlist`와 `length_exceptions`를 후보 pool로 사용하되, 실제 리뷰 큐에는 private local sample이 준비된 작품만 올린다. 원 후보 수는 별도의 pool count로 유지한다.

추천 근거는 기본적으로 접어 둔다. 먼저 실제 샘플을 읽고 반응을 고르게 해서 discovery 모델의 설명에 의한 anchoring을 줄인다.

각 답변은 날짜, canonical work key, verdict, reasons, 선택 태그/메모, 실제로 연 source 문자 수를 저장한다. `daily_taste:<date>:<canonical_key>`를 stable external id로 사용하므로 같은 날 같은 작품의 답변을 수정하면 기존 preference event를 교체하고 중복 가산하지 않는다.

상태 파일 `workspace/daily-taste-state.json`은 private이며 `scripts/runtime_sync.py`를 통해 iPhone runtime과 DevDrive canonical repository 사이에서 동기화한다.

## 목적

탐색 결과에 대한 실제 사용자 반응을 누적해 추천 정확도를 높이되, 현재 검색 요청이나 명시적 조건을 자동으로 훼손하지 않는다.

이 문서의 **취향 학습**과 `workspace/learning/operational-lessons.json`의 **운영/탐색 교훈 학습**은 분리한다. 전자는 “사용자가 무엇을 좋아하는가”를 배우고, 후자는 “어떤 오류가 반복됐고 어떤 해결책이 실제로 검증됐는가 / 어떤 탐색 절차가 오탐을 줄였는가”를 배운다. 운영 교훈은 `config/learning-policy.json`의 guard를 통과한 active lesson만 사용한다.

## 신호 계층

1. **Explicit verdict** — `love / like / neutral / dislike / exclude`
2. **Aspect reason** — 소재, 톤, 문체, 전개, 주인공, 캐릭터, 관계성, 로맨스, 세계관, 룰/시스템, 전략/추론, 개그, 어두움, 일상, 분량, 신선도, 결말, 장르혼합
3. **Feature tags** — 사용자가 자유롭게 적는 구체 취향. 예: `여성 주인공`, `건조한 문체`, `반복 데스게임`
4. **Strong implicit action** — 전체 번역 선택. 해당 작품을 positive example로 강하게 기록한다.

## 프로필 범위

- `GLOBAL`: 모든 탐색 그룹에 적용되는 기본 취향
- 특정 `profile_id`: 해당 조건 그룹에만 추가되는 취향
- 특정 프로필의 학습 모델은 `GLOBAL + profile-specific` 이벤트를 함께 본다.

## 자동 반영 범위

자동으로 가능한 것:

- hard filter 통과 후보 내부의 정렬 가중치 조정
- positive / negative example을 비교 기준으로 활용
- 본문 샘플링 우선순위 조정
- 반복되는 aspect/tag에 대한 soft preference 변경안 생성

자동으로 금지하는 것:

- `MUST`, `MUST NOT`, 최소 글자수 등 hard filter 변경
- 사용자가 명시한 현재 요청보다 과거 취향 우선
- 적은 표본으로 영구 취향 확정

## 제안 승격 규칙

초기값:

- 동일 signal이 최소 2회 등장
- 평균 절대 점수 1.0 이상
- confidence = `min(1, count / 5)`
- 조건을 만족하면 `proposed` soft-preference 제안 생성
- 사용자가 콘솔에서 승인해야 `config/search-profiles.json > learned_preferences`에 반영

## 다음 고도화 후보

- **exploration quota**: 상위 취향과 다른 후보 10~20%를 의도적으로 섞어 취향 고착 방지
- **time decay**: 오래된 반응의 가중치를 완만하게 감소
- **pairwise feedback**: “A보다 B가 낫다”를 직접 받아 점수보다 정밀한 선호 학습
- **reason extraction assist**: 사용자의 자유 메모에서 후보 태그를 제안하되 저장 전 승인
- **profile drift detector**: 한 프로필 안에서 상충되는 취향 군집이 생기면 새 조건 그룹 분리를 제안
- **false-positive audit**: 상위 추천이 반복해서 `dislike/exclude`를 받으면 어떤 검색 feature가 과대평가되었는지 역추적
- **serendipity lane**: 취향 적합도는 높지 않지만 신선도가 높은 작품을 별도 1~2개 유지

## 로컬 프라이버시

원시 피드백과 학습 모델은 `workspace/` 아래 private local state로 유지하며 GitHub Pages에 게시하지 않는다. 공개 페이지에는 필요하면 집계된 기능 상태만 노출하고 개인 취향 원문은 올리지 않는다.
