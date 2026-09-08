#!/bin/zsh
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
RUN_ID="$(TZ=UTC date +%Y%m%dT%H%M%S)-local-stage"
python3 scripts/automation_log.py --task daily_local_stage --action heartbeat --status started --run-id "$RUN_ID" --message "Daily local stage started" >/dev/null
python3 scripts/refresh_automation_status.py >/dev/null
STAMP="$(TZ=Asia/Seoul date +%Y-%m-%dT%H:%M:%S%z)"
mkdir -p workspace/run-logs
# Discovery and translation are executed by the scheduled ChatGPT/Steroids job.
# This local stage only refreshes durable state and validates the workspace.
if ! python3 scripts/validate_repo.py; then
  python3 scripts/automation_log.py --task daily_local_stage --action validate --status failed --run-id "$RUN_ID" --message "Repository validation failed" >/dev/null
  exit 1
fi
printf '%s local-stage-ok\n' "$STAMP" >> workspace/run-logs/daily.log
python3 scripts/automation_log.py --task daily_local_stage --action heartbeat --status done --run-id "$RUN_ID" --message "Daily local stage finished" >/dev/null
