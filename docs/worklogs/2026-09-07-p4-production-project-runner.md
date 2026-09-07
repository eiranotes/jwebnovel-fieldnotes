# Priority 4 production Project runner

## Scope
Move the already verified ChatGPT Project translation path from a one-work live E2E into the normal Fieldnotes production translation runner, without enabling the still-unconfigured daily schedule.

## Starting state
- Real `Fieldnotes` Project Instructions and immutable Sources were verified live.
- `beni-death-gamer` completed 2/2 chunks through one reusable Project worker with fresh source proof.
- Steroids Project routing/revival and the installed macOS runtime passed their full regression/deployment audit.
- Fieldnotes config still incorrectly declared Project translation blocked even though the live E2E had passed.

## Production gaps found
1. `translate_project.py` built a new work context and immediately asked the worker to retrieve it, but did not synchronize that new `WORK_<work_id>` source to the real Project first. Beni succeeded only because its sources were explicitly synchronized during the E2E setup.
2. The pinned work-context revision did not include `glossary.json`. A glossary update after one chunk could therefore leave the next Project Source revision stale even though the direct runtime glossary was current.
3. The daily job contract still described translation as a manual queue-task/model/result sequence rather than delegating the fail-closed lifecycle to the verified Project driver.
4. Automation status did not expose which translation backend/policy was active.

## Changes
- Project translation activation is now `verified_live`.
- `translate_project.py` requires that activation in addition to `backend=webgpt_project` and `allow_fallback=false`.
- Before every source probe, the driver synchronizes the exact immutable common/work context pair through `project_sources.synchronize(..., instructions=True)`.
  - An unchanged pair is a persisted no-op.
  - A new work or changed glossary/guide produces a new immutable source revision and is uploaded before worker execution.
  - Uncertain synchronization remains fail-closed; no worker task is submitted around it.
- `glossary.json` now participates in the guide/context revision fence.
- The daily automation contract now calls `translate_project.py` as the owner of Project sync, source proof, worker reuse, validation and transactional completion; it explicitly forbids manual/general-chat/local-worker/API fallback.
- Automation status now reports Project backend, activation, alias, source-proof policy and fallback policy.
- Human current-status documentation reflects Beni 2/2 complete and 8 chunks pending across four remaining works.

## Tests before live production smoke
- `python3 -m unittest discover -s tests -v`: **18/18 PASS**.
- Integration order is pinned as `source_sync -> project_source_probe -> translate_chunk` for every chunk.
- A new regression test proves a glossary mutation changes the Project guide revision.
- `git diff --check`: PASS.
- `refresh_automation_status.py` reports `webgpt_project / verified_live / require_source_probe=true / allow_fallback=false`.

## Schedule boundary
This does **not** enable the daily schedule. Search criteria and an exact Asia/Seoul clock time are still user inputs and remain unset. The verified translation backend can run independently while those two scheduling inputs remain blocked.

## Next live gate
Run the normal Project driver for `haikei-ashita-no-watashi` chunk `0001`. Success requires automatic source synchronization, a work-specific Project worker, fresh source retrieval proof, strict translation validation and exactly-once queue completion. No manual pre-upload is allowed for this smoke.

## Verdict
PASS for deterministic production-runner integration; live new-work smoke pending.
