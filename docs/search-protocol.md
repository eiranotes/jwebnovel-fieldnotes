# Search Protocol v0.4 — Parameterized Discovery

**Updated: 2026-09-06**

목표는 하나의 취향 프로필을 영구 고정하는 것이 아니다. **검색 절차는 재사용하고, 기준작·장르·제외조건·문체 가중치는 요청마다 교체**한다.

---

## 0. Research entry를 먼저 만든다

검색 전에 `YYYY-MM-DD-NN` 엔트리를 만든다. 결과가 나온 뒤 조건을 소급해서 고치지 않는다.

필수 필드:

- `entry_id`
- `date`
- `continuation_of` — 이전 조사 연장일 때만
- `reference_works[]`
- `hard_filters`
- `soft_preferences`
- `allowed_exceptions`
- `style_dimensions`
- `sampling_plan`
- `checked_at`

같은 날 기준작이나 요구조건이 바뀌면 새 엔트리다.

## 1. 요청을 네 종류의 조건으로 분해한다

### MUST

어기면 바로 `X` 처리하는 조건. 예: 50만 자 이상, 특정 장르, 비출판.

### MUST NOT

명시적 제외조건. 예: 전생, 악역영애, VRMMO, 게임 UI.

### PREFER

우선순위를 올리지만 위반해도 후보가 될 수 있는 조건. 예: 연재중, 여성주인공, 군상극.

### TOLERATE

사용자가 허용한 예외. 예: 연재중 우선이지만 완결·중단도 허용.

이 네 묶음을 섞지 않는다. 특히 `PREFER`를 hard filter처럼 사용하지 않는다.

### Global default — 300,000자

사용자가 별도 분량을 지정하지 않으면 **300,000자 이상을 기본 탐색 하한**으로 둔다. 읽을 만한 누적 분량이 있는 작품을 우선하기 위한 기본값이지, 절대적인 hard exclusion은 아니다.

우선순위는 다음과 같다.

1. 사용자가 분량을 명시하면 그 값이 global default를 덮어쓴다.
2. 분량 언급이 없으면 `default_min_chars = 300000`을 적용한다.
3. 300,000자 미만 작품은 원칙적으로 본 shortlist에서 제외한다.
4. 다만 **분량을 제외한 핵심 fingerprint와 요구조건이 모두 강하게 일치**하면 `LENGTH EXCEPTION`으로 별도 유지할 수 있다.

`LENGTH EXCEPTION`은 다음을 모두 만족해야 한다.

- 다른 hard filter 위반 없음
- 활성화된 핵심 style dimension에서 명백한 큰 차이 없음
- 단순 소재 일치가 아니라 구조·문체·전개 중 이번 요청의 핵심축이 A급으로 근접
- 짧다는 사실과 현재 분량을 결과 페이지에 명시

이 예외는 정상 분량 후보와 섞어 수량을 채우기 위한 장치가 아니다. **정확히 닮았지만 짧아서 버리기 아까운 작품을 보존하는 별도 lane**이다.

## 2. 기준작을 “작품명”이 아니라 fingerprint로 바꾼다

기준작이 있으면 1화만 읽고 태그를 붙이지 않는다. 최소 두 지점을 읽고 이번 요청에서 실제로 중요한 축을 고른다.

사용 가능한 축의 예:

- sentence hardness
- event throughput
- expository compression
- lyrical density
- dialogue ratio
- reaction ladder
- deadpan abnormality
- character-logic humor
- interiority
- combat ornamentation
- scene persistence
- worldbuilding density

**모든 요청에 같은 7축을 강제하지 않는다.** 활성 축만 선택하고 가중치 합을 100으로 만든다.

가능하면 반례도 하나 둔다. “이 작품처럼 되면 안 된다”는 기준이 있으면 `anti_reference`로 저장한다.

## 3. 후보 수집은 플랫폼의 구조화 필터를 먼저 쓴다

### Narou

나로우 공식 소설 API의 구조화 필드를 먼저 사용한다.

- `genre=201-202` 같은 장르 필터
- `minlen` / `maxlen` / `length`
- `nottensei=1` — 이세계 전생을 API 단계에서 제외
- `nottenni=1` — 전이도 제외하는 요청일 때만 사용
- `type=r / er / re` — 연재중·완결·전체 연재작을 요청별로 분리 수집
- `stop=2` — 장기중단작을 따로 찾고 싶을 때 별도 lane으로 수집
- `order`를 한 종류로 고정하지 않고 회전
- 제목·소개·키워드 기반 제외어는 2차 필터로 사용

**정렬 회전 예시:** `new → hyokaasc → hyokacntasc → old → lengthdesc → generalfirstup`. 인기순 한 번만 보면 묻힌 작품을 구조적으로 놓친다.

공식 API가 주는 `kaiwaritu`(대화율), `general_firstup`, `general_lastup`, 평가자 수, 북마크 수, 주간 유니크 등은 **선별 feature**로 저장한다. `buntai`는 실험 제공 필드이므로 hard gate로 쓰지 않는다.

### Kakuyomu

카쿠요무 자체 검색의 다음 필드를 먼저 사용한다.

- 장르
- `大長編 50万字〜`
- 연재 상태
- ★ 범위
- 제외어
- 제외조건 / 추출조건
- 공개일 / 갱신일
- 필요하면 콘테스트 조건

전역 기본값인 300,000자와 카쿠요무 UI의 분량 버킷이 정확히 일치하지 않을 수 있으므로, **가까운 넓은 분량 구간으로 수집한 뒤 작품별 표시 글자수에서 300,000자를 후처리**한다. 30만 자 미만도 곧바로 삭제하지 않고 고유사도 후보는 `underlength_queue`에 남긴다.

키워드는 최대한 넓게 수집하는 용도로 사용하고, 태그만으로 문체 통과 판정을 하지 않는다.

카쿠요무 검색결과에서 `書籍化` 배지가 직접 보이는 경우 Gate C에서 즉시 P3 후보로 처리한다. 다만 배지가 없다는 것만으로 P2를 주지는 않는다.

## 4. “중간 점수”를 cohort-relative visibility로 바꾼다

플랫폼·장르·연재연도마다 점수 분포가 다르다. `Narou 100–8,000pt` 같은 범위는 보조 힌트일 뿐이다.

기본 방식:

1. 이번 요청의 hard filter를 통과한 후보군을 만든다.
2. 플랫폼뿐 아니라 **장르 + 연재상태 + 초회 공개연도/연식 bucket**으로 cohort를 나눈다.
3. Narou는 `global_point`, 북마크 수, 평가자 수, 최근 point, 가능하면 주간 유니크를 기록한다.
4. Kakuyomu는 ★, 팔로워, 리뷰/응원 등 확보 가능한 노출 지표를 기록한다.
5. 각 지표를 log 변환 후 cohort 내 percentile로 바꾸고, `visibility_band`를 만든다.
6. 기본적으로 최상위 꼬리를 피하고 `mid-low / mid`를 우선 샘플한다.

점수 자체가 사용자 요청의 핵심이면 절대 범위와 분위수를 함께 기록한다.

## 5. 저비용 탈락 → 고비용 판정 순서로 간다

### Gate A — metadata

장르, 글자수, 연재 상태 등 구조화 필드로 제거. 분량 미지정 요청에서는 300,000자를 기본 probe 기준으로 사용하되, 고유사도 예외 후보를 완전히 버리지 않고 `underlength_queue`에 남긴다.

### Gate B — lexical disqualifier

제목·소개·키워드에서 전생/악역영애/게임 시스템 등 명시적 제외요소를 제거한다. 이 단계는 **탈락용**이지 통과용이 아니다.

Narou에서 공식 구조화 제외 플래그가 있는 조건(`nottensei`, `nottenni`)은 lexical filter보다 먼저 적용한다. `악役令嬢`, `乙女ゲーム`, `ステータス`, `レベル`, `スキル欄`처럼 구조화 플래그가 없는 조건만 lexical 후보 제거에 둔다.

### Gate C — quick publication flag

작품 페이지에서 `書籍化`, 출판사, 단행본 공지를 빠르게 확인한다. 명시되면 `P3`.

### Gate D — text sampling

여기서부터 실제 본문을 읽는다. 메타데이터 통과작 전체를 동일 깊이로 읽지 않는다.

### Gate E — publication cross-check

최종 shortlist만 제목 + 작가명 + `書籍化 / 書籍 / 出版`으로 교차검증해 `P2` 또는 `P3`를 확정한다.

이 순서로 외부 출판 검색과 장문 본문 읽기에 쓰는 시간을 줄인다.

## 6. 본문 샘플은 two-stage adaptive sampling

### Stage 1 — cheap prose probe

메타데이터 통과작은 우선 `S0` 한 지점만 읽는다. 여기서 기준작과 거리가 명백히 멀면 D로 내린다.

### Stage 2 — survivors only

S0에서 살아남은 작품만 추가로 읽는다.

- `S0` — 프롤로그가 아닌 첫 정상 회차
- `S1` — 전체의 약 10–25%
- `S2` — 전체의 약 50–70%

다음 경우 `S3`를 추가한다.

- 점수가 A/B 경계
- 초반과 중반 문체가 크게 달라짐
- 장기연재라 최근 문체 변화 가능성이 큼
- 기준작과 비슷하지만 한 축에서 판정이 애매함

이때 `S3`는 최근 연재부 또는 80–90% 지점을 본다.

각 샘플에서 **무슨 회차를 읽었는지 기록**한다. 다음 조사자가 같은 작품을 다시 처음부터 판정하지 않도록 한다.

가능하면 다음 단순 지표도 저장한다. 이 값들은 문체를 대신 판정하지 않고 **기준작과의 거리 확인용 보조치**다.

- 회차당 평균/중앙 문장 길이
- 문단 길이 분포
- 대화 비율
- 장면 안 상태 변화 횟수의 대략값
- 설명 문단이 행동 없이 연속되는 길이
- 긴 감정 독백이 차지하는 비중

## 7. eligibility와 similarity를 하나의 점수로 합치지 않는다

각 작품에 최소 두 값을 둔다.

- `eligibility`: hard filters 통과 여부
- `style_distance`: 이번 요청의 기준작/문체 요구와의 축별 거리

그리고 별도로:

- `publication_tier`: P0–P3
- `visibility_band`: low / mid-low / mid / mid-high / high
- `confidence`: low / medium / high

사용자가 **명시적으로 최소 분량을 hard condition으로 지정한 경우** 그보다 짧으면 A가 되지 않는다. 반대로 분량이 global default 300,000자에만 미달하고 나머지 핵심축이 모두 매우 가깝다면 `A-LE` 또는 `B-LE`처럼 `LENGTH EXCEPTION`으로 별도 표시할 수 있다. 모든 메타 조건을 만족해도 본문이 다르면 Q/D다.

## 8. 0–100 단일점수보다 reference-relative vector를 우선한다

기준작이 바뀌면 기존 `Sentence hardness 20` 같은 가중치를 복사하지 않는다.

절차:

1. 기준작에서 5–10개의 잠재 축을 추출
2. 사용자의 표현과 직접 연결되는 4–8개만 활성화
3. 핵심 2–3축에 높은 가중치
4. 보조축에는 낮은 가중치
5. 반례작이 있으면 반례와 가장 크게 갈리는 축을 점검

각 활성 축은 기준작을 `0`으로 놓고 후보가 얼마나 다른지를 기록한다.

예시:

```text
sentence_hardness      +1   # 기준작보다 조금 더 장식적
event_throughput       -1   # 기준작보다 사건 밀도가 조금 낮음
deadpan_abnormality     0   # 거의 같은 온도
interiority            +2   # 내면 서술이 훨씬 많음
```

기본 거리 척도는 `0–4`다.

- `0` 거의 같은 범위
- `1` 작은 차이
- `2` 독서감에서 체감되는 차이
- `3` 핵심 축에서 큰 차이
- `4` 사실상 다른 계열

가중 합산값은 내부 정렬에만 사용한다. 공개 페이지에서는 **A/B/Q/D/X + 축별 차이 + confidence**를 우선 표시한다. 기존 엔트리의 0–100 점수는 역사적 기록으로 남긴다.

## 9. A / B / Q / D / X

- `A` — hard gate 통과 + 기준작/요구감각에 강하게 근접
- `B` — hard gate 통과 + 일부 축에서 참고 가치가 큼
- `Q` — 아직 본문/출판 검증이 덜 됨
- `D` — 읽어본 뒤 해당 요청에서 우선순위 하향
- `X` — hard filter 위반
- `A-LE / B-LE` — global 300,000자 기본값에만 미달하지만, 분량 외 핵심 조건이 매우 강하게 맞는 length exception

고정 점수 컷보다 **샘플의 증거와 차이 설명**을 우선한다.

## 10. 출판 확인은 P0–P3로 기록한다

- `P0` — 확인 안 함
- `P1` — 작품 페이지에서 상업판 표시 없음
- `P2` — 작품 페이지 + 제목/작가 외부 검색에서도 상업판 확인 못함
- `P3` — 상업출판 확인

`P2`를 “절대 미출판”이라고 표현하지 않는다.

## 11. 크로스포스트는 작품 하나로 병합한다

Narou와 Kakuyomu 양쪽에 같은 작품이 있으면 두 후보로 세지 않는다.

정규화 키:

```text
normalized_title + author
```

플랫폼별 URL·점수·갱신일은 `platform_instances[]`에 각각 저장한다.

## 12. 탐색을 언제 멈출지 정한다

후보 수를 임의로 20편 채우는 대신 **marginal yield**를 본다.

기본 종료조건:

- 20개 후보 배치를 두 번 연속 추가했는데 새 A/B가 각 배치의 10% 미만
- 새로운 검색어/정렬을 추가해도 상위 shortlist가 거의 변하지 않음
- 사용자 요청 수량을 충족했고 Q의 추가검증이 우선인 상태

수량을 채우기 위해 질 낮은 작품을 끼워 넣지 않는다.

## 13. 다음 요청에 이전 취향을 자동 이식하지 않는다

새 요청은 항상 새 request snapshot에서 시작한다.

- 이전 기준작과 같고 “더 찾아봐” → `continuation_of`
- 기준작 변경 → 새 fingerprint
- 글자수/장르/제외조건 변경 → 새 hard filters
- 문체 요구가 달라짐 → 새 style dimensions

과거 엔트리는 참고 자료이지 묵시적 필터가 아니다.

## 14. cheap features를 이용해 본문 읽기 순서를 최적화한다

기준작에서 미리 뽑을 수 있는 정량 신호를 후보의 우선순위에만 사용한다.

Narou에서 특히 유용한 것:

- `kaiwaritu` — 대화율
- `length / general_all_no` — 회차당 평균 글자수 근사
- `general_firstup / general_lastup` — 연재 연식과 활동성
- `isstop` — 장기중단 여부
- `global_point / all_hyoka_cnt / fav_novel_cnt / weekly_unique` — 노출도 cohort 계산
- `buntai` — 실험 feature, 참고용

예를 들어 기준작이 짧은 문단·높은 사건 처리량인데 후보가 회차당 평균 15,000자이고 대화율도 극단적으로 낮다면 S0 읽기 우선순위를 낮출 수 있다. **이 feature만으로 탈락시키지는 않는다.**

## 15. lane sampling으로 선호조건 편향을 통제한다

“연재중 우선, 완결/중단도 허용”처럼 PREFER가 있는 경우 한 검색 결과에 섞지 않는다.

예시 allocation:

- ongoing lane 60%
- completed lane 25%
- hiatus lane 15%

비율은 요청마다 조정한다. 이렇게 하면 연재중 작품이 많다는 이유로 중단작 탐색이 사실상 사라지는 문제를 막는다.

## 16. Search loop v0.4

```text
REQUEST SNAPSHOT
  ↓
REFERENCE / ANTI-REFERENCE FINGERPRINT
  ↓
STRUCTURED HARVEST — lanes × sort rotations
  ↓
METADATA GATE
  ↓
DEFAULT 300K LENGTH LANE
  ├─ 300K+ → normal lane
  └─ <300K → underlength queue
                 ↓ only if core fit is very high
              LENGTH EXCEPTION
  ↓
STRUCTURED EXCLUSION FLAGS
  ↓
LEXICAL DISQUALIFIER
  ↓
QUICK PUBLICATION FLAG
  ↓
CHEAP FEATURE PRIORITY
  ↓
S0 PROBE
  ↓
SURVIVORS: S1 / S2 / optional S3
  ↓
REFERENCE-RELATIVE STYLE DISTANCE
  ↓
A / B / Q / D / X
  ↓
FINAL PUBLICATION CROSS-CHECK
  ↓
MARGINAL-YIELD STOP CHECK
```

## 실패 패턴

- 기준작이 바뀌었는데 이전 가중치를 그대로 재사용
- 인기순 검색 한 번으로 후보군을 대표한다고 가정
- `ブラックユーモア` 같은 태그를 문체 증거로 사용
- Narou pt와 Kakuyomu ★를 같은 숫자축으로 비교
- 시리즈 총 글자 수를 개별 작품 글자 수로 오인
- PREFER 조건을 hard filter로 사용
- 출판 여부 전체검증을 후보 수집 초반에 수행해 탐색 시간을 소모
- 20편이라는 수량을 맞추기 위해 D급 후보를 승격
- 정량 feature가 비슷하다는 이유로 실제 본문 확인을 생략
- 0–100 점수를 객관적 품질점수처럼 제시

## Method sources

- Narou official novel API: https://dev.syosetu.com/man/api/
- Kakuyomu search help: https://kakuyomu.jp/help/entry/trends
- Kakuyomu 500k+ search filter announcement: https://kakuyomu.jp/info/entry/search-long-long-story

플랫폼 UI와 API는 바뀔 수 있으므로 새 조사일에 필터 존재 여부를 다시 확인한다.
