# Discovery Filter Checklist

나중에 사용자가 채울 조건 목록입니다.

## 공통

- 소스: Narou / Kakuyomu / 둘 다
- 포함 키워드
- 제외 키워드
- 최소 회차 수
- 최대 회차 수
- 완결작 포함 여부
- 연재 중만 볼지
- 최소 최근 업데이트 시점
- 하루 신규 후보 상한
- 이미 본 작품 재노출 금지 기간

## Narou

- API 정렬: `new`, `weeklypoint`, `monthlypoint`, `hyoka`, `favnovelcnt` 등
- 장르 코드
- 최소 총점
- 최소 북마크 수
- 검색어 대상: 제목/작가/키워드/소개문

## Kakuyomu

- 검색어
- include/exclude term
- 검색 결과 페이지 수
- 태그 포함/제외
- 작품 상세에서 로컬 검증할 최소 회차 수

## 후처리 우선순위

- 점수/북마크/최근성 가중치
- 태그 선호도
- 제목/소개문 LLM 분류 점수
- 같은 작가 중복 제한
