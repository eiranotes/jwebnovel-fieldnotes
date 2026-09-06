# Current Status

기준일: 2026-09-06

## 구현 완료

- Narou 공식 Novel API 기반 조건 검색
- Kakuyomu 공개 검색 결과 기반 작품 탐색
- 작품 URL/ID 기준 SQLite dedupe
- 작품 메타데이터 수집
- 사이트별 앞 N화 다운로드, 기본 5화
- 회차별 원문 + 메타 sidecar 저장
- 1~5화 단일 TXT 병합
- `<ruby>`를 `표기《읽기》`로 보존
- 작품별 `glossary.json` 생성 및 루비 seed 누적
- 청크 단위 번역
- 이전 번역 꼬리 + 작품 용어집을 다음 청크에 전달
- 청크 SHA-256 기반 번역 재개/skip
- 원문/번역 병렬 Markdown 생성
- `state.sqlite3` + 작품별 `state.json` 이중 상태 기록
- 정적 `site/index.html` 상태 페이지 생성
- macOS launchd 일일 실행 installer
- 실행/설계/필터/경로 문서화

## 검증 완료

### Unit

- 루비/rp 처리
- 청크 분할
- 작품 dedupe
- 예제 설정 로딩
- 번역 청크 resume 및 glossary update

결과: `5 tests / OK`

### Live smoke

- Narou 실제 검색 → 메타데이터 → 5화 다운로드 → 병합 성공
- Kakuyomu 실제 검색 → 메타데이터 → 5화 다운로드 → 병합 성공
- 동일 smoke 설정 즉시 재실행 시 `processed = 0` 확인
- Kakuyomu 실제 회차 제목 `.widget-episodeTitle` 검증 완료

## 현재 미활성

아래 항목은 구현 문제가 아니라 사용자 설정값이 아직 없어서 활성화하지 않았습니다.

1. 실제 일일 검색 조건: `config.toml`의 discovery 블록이 기본 `enabled = false`
2. 번역 provider: `translation.enabled = false`, API key/model 미설정
3. launchd 스케줄: 실행 시각 미확정이라 installer만 제공, 실제 등록하지 않음

## 다음 입력이 필요한 값

- 검색 포함/제외 키워드
- 최소 회차/점수/북마크 등 필터
- 하루 신규 작품 상한
- 번역 모델/provider
- 매일 실행 시각

검색조건 세부 항목은 `docs/FILTERS.md` 참조.
