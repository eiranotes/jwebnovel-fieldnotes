# Fieldnotes 무인 자동화 상태 감시 — 읽기 전용

\`scripts/automation_health.py\`는 작업 큐·원본 매니페스트·워커 상태를
읽어서 진단한다. 기존 번역 모델 드라이버와 영수증 규약을 대체하지 않는다.

\`\`\`bash
python3 scripts/automation_health.py
python3 scripts/automation_health.py --worker-status /ABSOLUTE/TRUSTED/PATH/model-worker-heartbeat.json
python3 -m unittest discover -s tests -p 'test_automation_health.py'
\`\`\`

## 정확한 워커 판정

* 모델 번역 capability는 \`fieldnotes.karu.project.translate\`이다.
* \`fieldnotes.queue.inspect\` 워커는 **수신·대기열 상태 점검만 가능**하다.
  번역 실행이 가능한 것으로 간주하면 안 된다.
* 정상 워커 증거는 \`workspace=shared-automation\`, \`status=ready\`,
  \`capabilities[]\`에 모델 번역 capability가 존재하고,
  \`observed_at\`이 기본 5분 이내인 신뢰된 heartbeat JSON이다.
* heartbeat 자체를 생산하는 Eira 운영 어댑터는 별도로 설치해야 한다.
  파일이 없으면 \`model_worker.status=unknown\`이며, 임의로
  새 프로세스가 준비됐다고 가정하지 않는다.
* 청크의 최근 검증 상태가 기본 3시간 이상 정체되고 실제 모델
  워커가 정상이라는 증거가 있을 때만 \`stalled\`이다.
  워커를 관측할 수 없으면 \`awaiting_worker_observation\`으로 분리한다.

예시 heartbeat 구조:

\`\`\`json
{
  "workspace": "shared-automation",
  "observed_at": "2026-10-09T01:00:00Z",
  "status": "ready",
  "capabilities": ["fieldnotes.karu.project.translate"]
}
\`\`\`

heartbeat는 **실제 Eira 런타임의 인증된 관측 결과**로만 생성해야 한다.
수동으로 이 JSON을 만들어 워커가 정상이라고 주장하면 안 된다.

## 오류별 조치

| 구분 | 의미 | 허용 조치 |
|---|---|---|
| \`awaiting_worker_observation\` | 번역 큐는 있으나 워커 증거 없음 | 작업 유지·연결 상태 조사 |
| \`worker_unavailable\` | 워커 미지원 capability/오프라인/heartbeat 만료 | 워커 복구, 재번역 제출 금지 |
| \`stalled\` | 워커는 살아 있으나 청크가 오래 정체 | 원본 task/operation/receipt 대조 |
| \`invalid_manifest\` | 정본 청크 스키마 또는 JSON 오류 | 파일 백업 후 수동 복구 |
| \`source_or_manifest_missing\` | 예정 상태인데 준비된 청크 없음 | 원문 수집 단계 확인 |

모든 결과는 읽기 전용이다. 이 도구는 \`translation_queue.py next\`,
\`translation_queue.py complete\`, WebGPT 제출, 브라우저 제어를
호출하지 않는다. 임의 재시도로 작업 핸들이 중복 발급되는 일을 막는다.

## Eira 연동 시의 단계

1. 프로필 1의 발견·예약과 프로필 2의 번역 실행을 공용 Fabric 영속 큐로 연결.
2. 실제 모델 워커가 주기적으로 인증된 heartbeat 상태를 생성.
3. \`automation_health.py\`를 읽기 전용 관측 드라이버로 등록.
4. 단계별 문제를 관리 화면에 표시. 등록되지 않은 모델 번역 워커는
   상태만 경고하고 번역 제출로 자동 보상하지 않는다.
5. 정본 영수증 검증 후에만 기존 브라우저 탭·세션 회수.
6. 운영 Mac 연결 후 재부팅·잠금·MCP 터널 단절 E2E를 검증하고 승격.

**주의:** GitHub 반영이 Mac 현장 배포나 번역 재시작을 의미하지 않는다.
