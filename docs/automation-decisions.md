# Daily Discovery Automation — Decisions

Updated: 2026-09-06

## Purpose

매일 한 번, 사용자가 정의한 검색 프로필별로 Narou/Kakuyomu 작품을 탐색하고 날짜별 research entry를 추가한다. 상위 후보 중 source pipeline 대상은 기본 5개다.

## Non-negotiable decisions

1. **Daily research entry**
   - 한 날짜에 프로필이 여러 개면 각각 `YYYY-MM-DD-NN` 엔트리를 만든다.
   - 같은 프로필의 연속 탐색이면 `continuation_of`를 연결한다.

2. **Default length**
   - 사용자 지정이 없으면 300,000자 이상.
   - 분량 외 핵심조건이 거의 전부 맞는 작품만 `LENGTH EXCEPTION`으로 별도 유지.

3. **Public vs private**
   - GitHub Pages: 메타데이터, 탐색 근거, shortlist, 진행상태만 공개.
   - 원문 전문 / 한국어 전문 / 병렬 본문: 로컬 workspace 전용. Git에는 올리지 않는다.

4. **Source acquisition gate**
   - Narou 본문 자동 scraping/downloading은 구현하지 않는다.
   - Kakuyomu 타인 작품의 공식 백업 다운로드도 자동화 대상으로 보지 않는다.
   - 사용자가 합법적으로 확보하여 `source_inbox/`에 넣은 TXT/ZIP만 이후 파이프라인이 자동 처리한다.

5. **Translation continuity**
   - 작품별 merged JA → chunk manifest → pending/done checkpoint.
   - 다음 실행은 가장 오래된 pending chunk부터 이어서 처리.
   - 각 task에는 이전 청크 tail, 다음 청크 head, glossary를 같이 제공.
   - 인명/지명/고유명사는 glossary를 우선하고 ruby/furigana/metadata를 근거로 결정한다.

6. **Steroids-first execution**
   - 파일 생성, 상태 갱신, Git commit/push, Pages 검증은 Chat On Steroids Core를 기본 실행 채널로 사용.
   - 웹 탐색/검색은 ChatGPT web 기능을 사용하고 결과를 Steroids가 저장소에 기록.

## Platform acquisition constraints verified on 2026-09-06

- Narou: 독자용 TXT 다운로드 기능은 2026-03-26 폐지. 소설 API는 메타데이터 검색용이며 본문 대량수집 용도가 아님.
- Narou: API 외 자동화된 데이터 수집은 사이트 정책상 피한다.
- Kakuyomu: 공식 작품 다운로드/백업은 작가가 자신의 작품을 내려받는 기능 중심. 제3자 공개 작품을 일괄 TXT로 받는 파이프라인으로 사용하지 않는다.

따라서 `discover → top5 → source acquisition gate → merge/chunk/translate`를 분리한다.

## Daily run order

```text
01 load search profiles
02 discover candidates
03 apply default 300k gate + length exceptions
04 read/reference-sample survivors
05 produce dated entry + update archive
06 select top N (default 5) for source pipeline
07 check source_inbox availability
08 if source exists: normalize → merge → chunk
09 resume oldest pending translation chunk(s)
10 update glossary / state / local parallel view
11 refresh public automation-status.json
12 validate → commit → push → GitHub Pages verify
```

## Pending user decisions

- exact daily clock time (Asia/Seoul)
- search profiles / reference works / exclusions / preferences
- desired number of shortlist results per profile
- whether commercial publications are excluded by default
- whether completed / hiatus works are allowed and at what priority
- translation throughput cap per daily run
