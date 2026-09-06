# Search Protocol v0.1

**기준일: 2026-09-06**

이 문서는 탐색이 다시 “그냥 괜찮은 정통 판타지 추천”으로 흐르는 것을 막기 위한 판정 규칙이다.

## 1. Reference fingerprint

기준작: 『賢者フィロフィーと気苦労の絶えない悪魔之書』  
https://ncode.syosetu.com/n2066cv/

### 문체 특징

1. **Functional sentences** — 묘사는 역할을 마치면 바로 빠진다.
2. **High event throughput** — 설명 다음에 행동·문제·결과가 빠르게 붙는다.
3. **Deadpan abnormality** — 폭력, 재난, 기행을 자동으로 감정적 클라이맥스로 만들지 않는다.
4. **Low lyrical drag** — 풍경과 내면이 장면을 오래 정지시키지 않는다.
5. **Character-logic humor** — 농담보다 비정상적 실용논리에서 웃음이 생긴다.
6. **Serious world / unstable people** — 세계의 규칙은 진지하지만 인물은 정상일 필요가 없다.
7. **Low reaction ladder** — 충격→감탄→설명→찬사의 반복이 적다.

## 2. Hard metadata filters

| 항목 | 규칙 |
|---|---|
| 플랫폼 | Narou / Kakuyomu |
| 장르 | 하이판타지 / 로우판타지 |
| 분량 | 원칙적으로 500,000자 이상 |
| 전생 | 제외 |
| 악역영애 / 오토메게임 | 제외 |
| 게임 세계 / VRMMO | 제외 |
| 시스템 UI | 레벨·스테이터스·스킬창이 핵심이면 제외 |
| 상업출판 | 확인되면 제외 |
| 인기도 | 현행 상위 랭킹·대형 히트작 회피 |
| 연재 | 연재중 우선, 완결·중단 허용 |

### 탐색용 인기도 밴드

절대적인 품질 기준이 아니라 후보 발굴을 위한 범위다.

- Narou: 대략 **100–8,000pt** 우선. 설정·문체가 가까우면 100pt 미만도 확인.
- Kakuyomu: 대략 **★50–1,000** 우선. 별점만 보지 않고 팔로워·랭킹 노출도 같이 확인.
- 점수가 높아도 문체 유사도가 매우 높으면 예외적으로 유지.

## 3. Publication check

각 작품마다:

1. 작품 정보에서 `書籍化`, `出版`, 출판사명, 발매권수 확인
2. 정확한 제목 + 작가명 + `書籍化` / `書籍` / `出版` 검색
3. 상업판 확인 시 제외
4. 없으면 `current check에서 commercial edition not found`로 기록

## 4. Candidate harvesting

다음 키워드는 후보 수집에만 쓴다. 통과 근거로 쓰지 않는다.

- `現地主人公`
- `非テンプレ`
- `ブラックユーモア`
- `群像劇`
- `オリジナル戦記`
- `長編`
- `完結` / `連載中`

## 5. Text sampling rule

시놉시스만 보고 문체를 판정하지 않는다.

가능하면 세 지점을 읽는다.

- **S0:** 1화 또는 프롤로그 직후 첫 정상 회차
- **S1:** 전체의 약 10–25%
- **S2:** 전체의 약 50–75%

## 6. Editorial fit score

| 항목 | 가중치 | 판정 질문 |
|---|---:|---|
| Sentence hardness | 20 | 문장이 말하고 행동하고 넘어가는가 |
| Event throughput | 20 | 한 장면 안에서 실제 상태 변화가 자주 일어나는가 |
| Expository compression | 15 | 설정 설명이 장면을 멈추지 않는가 |
| Deadpan abnormality | 15 | 비정상적 사건을 과잉 감정 없이 처리하는가 |
| Character-logic humor | 10 | 인물의 이상한 실용논리에서 웃음이 나는가 |
| Low sentimentality | 10 | 독자가 느낄 감정을 반복적으로 설명하지 않는가 |
| Low ornamental drag | 10 | 수사와 장식 묘사가 통제되어 있는가 |

### 해석

- **85–100:** A
- **75–84:** A/B 경계, 추가 샘플
- **65–74:** B
- **<65:** 보통 D, 특정 참고점이 있을 때만 유지

## 7. 판정 필드 분리

각 후보는 반드시 따로 기록한다.

- `metadata_fit`
- `prose_fit`
- `publication_check`
- `status`

하나의 “추천” 플래그로 합치지 않는다.

## 8. Search loop

```text
HARVEST
  ↓
HARD FILTER
  ↓
PUBLICATION CHECK
  ↓
3-POINT TEXT SAMPLE
  ↓
EDITORIAL FIT SCORE
  ↓
A / B / Q / D
  ↓
RE-SAMPLE BORDERLINE WORKS
```

## 9. 실패 패턴

- 정통 판타지라는 이유만으로 느리고 장식적인 작품을 추천
- 주인공이 잔혹하다는 이유만으로 건조한 문체라고 간주
- `ブラックユーモア` 태그만 보고 본문 확인 없이 통과
- Narou pt와 Kakuyomu ★를 같은 척도로 비교
- 시리즈 총 글자 수를 개별 작품 50만 자로 오인
