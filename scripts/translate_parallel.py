#!/usr/bin/env python3
"""Run several Fieldnotes works concurrently with globally staggered Project requests.

Each subprocess translates at most one chunk.  The scheduler never runs two chunks from the
same work at once, keeps at most ``--workers`` distinct works active, and enforces a minimum
gap between launches.  Because translate_project.py is resumable, an already-accepted Project
operation is resumed rather than submitted a second time after a driver interruption.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from learning_store import safe_observe

ROOT = Path(__file__).resolve().parent.parent


def pending(entry: str) -> list[dict]:
    proc = subprocess.run(
        [sys.executable, str(ROOT/'scripts'/'translation_queue.py'), 'status'],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    data = json.loads(proc.stdout)
    rows = [row for row in data.get('works', []) if row.get('entry_id') == entry and int(row.get('pending_chunks', 0)) > 0]
    # Keep already-open/revivable work conversations hot before creating another Project chat.
    # This bounds browser footprint as well as model concurrency: with two worker slots, a
    # sleeping work that still owns a tab should consume the next slot before a third work is
    # introduced into Chrome merely because its queue row happened to sort earlier.
    def has_conversation(row: dict) -> bool:
        mapping = ROOT/'workspace'/'automation-runs'/'backend'/row['work_id']/'translator'/'worker.json'
        try:
            return bool(json.loads(mapping.read_text(encoding='utf-8')).get('conversation_id'))
        except (OSError, ValueError, TypeError):
            return False
    ordered = sorted(enumerate(rows), key=lambda item: (not has_conversation(item[1]), item[0]))
    return [row for _, row in ordered]


@dataclass
class Slot:
    work_id: str
    title: str
    process: subprocess.Popen
    started: float


def launch(entry: str, row: dict) -> Slot:
    cmd = [
        sys.executable, str(ROOT/'scripts'/'translate_project.py'),
        '--entry', entry, '--work', row['work_id'], '--max-chunks', '1',
    ]
    proc = subprocess.Popen(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return Slot(row['work_id'], str(row.get('title') or row['work_id']), proc, time.monotonic())


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--entry', required=True)
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--launch-gap', type=float, default=30.0)
    args = p.parse_args()
    # Chat On Steroids deliberately caps browser-backed workers at two: three concurrent
    # ChatGPT web workers reproducibly trip the conversation rate limiter. Keep this runner
    # aligned with that transport invariant instead of creating doomed extra tabs.
    if not 1 <= args.workers <= 2:
        raise SystemExit('--workers must be 1..2 for ChatGPT web transport')
    if args.launch_gap < 0:
        raise SystemExit('--launch-gap must be >= 0')

    active: dict[str, Slot] = {}
    completed_chunks = 0
    failures: list[dict] = []
    blocked_works: set[str] = set()
    stop_scheduling = False
    last_launch = 0.0
    started_at = time.time()

    while True:
        # Reap before scheduling. Output is emitted as one compact line per chunk so a long
        # benchmark can be watched without dumping model payloads into the terminal.
        for wid, slot in list(active.items()):
            code = slot.process.poll()
            if code is None:
                continue
            output = slot.process.stdout.read() if slot.process.stdout else ''
            del active[wid]
            elapsed = time.monotonic() - slot.started
            if code == 0:
                completed_chunks += 1
                print(json.dumps({'event':'chunk_done','work_id':wid,'title':slot.title,'seconds':round(elapsed,2)}, ensure_ascii=False), flush=True)
            else:
                error = None
                for line in reversed([x.strip() for x in output.splitlines() if x.strip()]):
                    try:
                        parsed = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(parsed, dict) and parsed.get('status') == 'blocked':
                        error = parsed.get('error')
                        break
                blocked_works.add(wid)
                safe_observe(
                    'translation', str(error or f'runner_exit_{code}'), 'observed',
                    scope='orchestrator', note=f'work={wid}; runner_exit={code}', root=ROOT,
                )
                failures.append({'work_id':wid,'title':slot.title,'code':code,'error':error,'tail':output[-800:]})
                print(json.dumps({'event':'chunk_failed','work_id':wid,'title':slot.title,'code':code,'error':error,'seconds':round(elapsed,2),'tail':output[-300:]}, ensure_ascii=False), flush=True)
                # Transport/submission ambiguity or a bootstrap failure is account/session scoped
                # enough that launching more browser work only amplifies a possible 429. Stop
                # creating new work; already-active accepted jobs are allowed to finish.
                if error in {'spawn_failed','rate_limited','OPERATION_SUBMISSION_UNCERTAIN','PROJECT_WORKER_BOOTSTRAP_FAILED','WORKER_RESULT_TIMEOUT','CHATGPT_CONVERSATION_RATE_LIMITED'}:
                    stop_scheduling = True

        queue = pending(args.entry)
        if (not queue or stop_scheduling) and not active:
            break

        # Keep one active process per work. A work returning to the queue after chunk N may run
        # chunk N+1 once a slot and the global launch-gap are available.
        candidates = [row for row in queue if row['work_id'] not in active and row['work_id'] not in blocked_works]
        now_mono = time.monotonic()
        if not stop_scheduling and len(active) < args.workers and candidates and now_mono - last_launch >= args.launch_gap:
            row = candidates[0]
            slot = launch(args.entry, row)
            active[row['work_id']] = slot
            last_launch = time.monotonic()
            print(json.dumps({'event':'launched','work_id':row['work_id'],'title':row.get('title'),'active':len(active)}, ensure_ascii=False), flush=True)
            continue

        time.sleep(0.5)

    print(json.dumps({
        'status':'complete' if not failures else 'completed_with_failures',
        'entry_id':args.entry,
        'workers':args.workers,
        'launch_gap_seconds':args.launch_gap,
        'completed_chunks':completed_chunks,
        'failures':failures,
        'wall_seconds':round(time.time()-started_at,2),
    }, ensure_ascii=False), flush=True)
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())
