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

4. **Source acquisition boundary**
   - 탐색 결과의 상위 작품에 한해 기본 5개 공개 회차를 개인 로컬 workspace로 수집한다.
   - 전체 작품 archive를 만들지 않고 source pipeline에 필요한 제한 범위만 저장한다.
   - acquisition manifest가 같으면 재다운로드하지 않는다.
   - 직접 제공 TXT/ZIP은 계속 fallback으로 지원한다.

5. **Translation continuity**
   - 작품별 merged JA → chunk manifest → pending/done checkpoint.
   - 다음 실행은 가장 오래된 pending chunk부터 이어서 처리.
   - 각 task에는 이전 청크 tail, 다음 청크 head, glossary를 같이 제공.
   - 인명/지명/고유명사는 glossary를 우선하고 ruby/furigana/metadata를 근거로 결정한다.

6. **Steroids-first execution**
   - 파일 생성, 상태 갱신, Git commit/push, Pages 검증은 Chat On Steroids Core를 기본 실행 채널로 사용.
   - 웹 탐색/검색은 ChatGPT web 기능을 사용하고 결과를 Steroids가 저장소에 기록.

7. **Profile selection and rotation**
   - 페이지에서 여러 검색 그룹을 동시에 `NEXT SEARCH`로 지정할 수 있다.
   - 지정이 없으면 round-robin / least-recently-run / date-seeded random / all-enabled 중 설정된 fallback을 사용한다.

8. **Persistent duplicate index**
   - 모든 기존 후보를 `data/work-index.json`에 축적하고 새 탐색 전에 strict dedupe한다.
   - 제목+작가가 확보되면 플랫폼을 넘어 같은 작품으로 묶는다.

9. **User-selected full translation lane**
   - 기본 shortlist 취득은 계속 앞 5화만 사용한다.
   - 사용자가 전체 번역을 명시한 작품만 별도 full-work workspace에서 전 회차 취득/병합/번역한다.

10. **Automation observability and private delivery**
   - 자동화 작업 경계마다 로그를 남기고 공개 페이지에는 sanitized summary만 표시한다.
   - 원문/번역 파일 전달은 loopback private console + Tailscale Serve로만 제공한다.

## Acquisition implementation verified on 2026-09-06

- Discovery remains metadata/search driven.
- A separate worker handles only the selected work URL and first N readable episodes.
- Source and translation payloads remain private/local and are not committed or published.

Flow: `discover → shortlist → top5 → first5 acquisition → merge/chunk → translate`.

## Daily run order

```text
01 load search profiles
02 discover candidates
03 apply default 300k gate + length exceptions
04 read/reference-sample survivors
05 produce dated entry + update archive
06 select top N (default 5) for source pipeline
07 acquire selected first N public episodes into private source_inbox
08 normalize → merge → chunk
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
