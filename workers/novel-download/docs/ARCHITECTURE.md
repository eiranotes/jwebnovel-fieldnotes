# Architecture

## 목표

1. Narou / Kakuyomu 검색 조건을 여러 개 독립적으로 실행한다.
2. URL/작품 ID 기준으로 신규 작품만 큐에 넣는다.
3. 작품당 앞 N화(기본 5화)를 텍스트로 저장하고 하나의 원문 파일로 병합한다.
4. 루비 정보를 번역 힌트와 용어집 seed로 보존한다.
5. 번역은 청크 단위로 진행하고 청크 해시/상태를 저장해 중단 후 재개한다.
6. 원문과 번역문을 모두 보존하고 정적 HTML 보고서를 만든다.
7. 모든 실행은 idempotent하게 만들어 같은 날 여러 번 실행해도 이미 완료된 단계는 재사용한다.

## 디렉터리

```text
data/
  state.sqlite3
  works/
    narou/<ncode>/
      metadata.json
      state.json
      glossary.json
      raw/
        001.txt
        002.txt
        ...
      merged/
        original_001-005.txt
      chunks/
        0001.source.txt
        0001.translation.txt
        0001.json
      translated/
        ko_001-005.txt
      bilingual/
        ja-ko_001-005.md
```

## 상태 모델

`DISCOVERED -> METADATA_READY -> DOWNLOADED -> TRANSLATING -> TRANSLATED`

오류는 단계 상태를 덮어쓰지 않고 `last_error`에 기록합니다. 다음 실행에서 완료되지 않은 단계만 재시도합니다.

## 사이트 어댑터

- `novelpipeline/sites/narou.py`: Narou 공식 Novel API 검색 + 공개 작품/회차 HTML 파싱
- `novelpipeline/sites/kakuyomu.py`: Kakuyomu 공개 검색 HTML + 작품/회차 HTML 파싱

사이트 HTML 변경 영향은 어댑터 내부 selector fallback으로 제한합니다.

## 번역

기본 provider는 OpenAI-compatible Chat Completions endpoint입니다. 출력은 JSON으로 강제하며 `translation`, `glossary_updates`를 받습니다. 각 청크마다 이전 번역 꼬리와 작품 용어집을 전달해 인명/용어 흔들림을 줄입니다.
