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
- Before every source probe, the driver requires the immutable `GLOBAL_CONTEXT` Project Source as a stable retrieval anchor.
  - Persistent Project Instructions are setup state, not per-chunk synchronization state. The browser intentionally refuses to overwrite an existing non-empty instruction field automatically.
  - Work-specific metadata, glossary, adjacent context and chapter text are read from the exact local task JSON, so a mutable `WORK_<work_id>` upload is no longer part of the production critical path.
  - A prior verified UI listing receipt can avoid a redundant upload of an unchanged immutable anchor. A fresh model source-probe still follows, so provider-side deletion/index loss remains fail-closed.
  - Current policy reaches each translation through `GLOBAL_CONTEXT` plus the per-turn Project-worker bootstrap/task contract.
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

## First live new-work attempt
The normal production command automatically synchronized `GLOBAL_CONTEXT_v0001_876141ee0b6c.md` plus the newly generated `WORK_haikei-ashita-no-watashi_v0001_f372e5a141e2.md`. The browser-owned Project UI receipt was complete at 05:12:43 UTC and listed both exact filenames with Instructions saved. A new exact-target worker (`worker-30`, conversation `6a9e47d0-da48-83ee-b38c-372bc3ddb8d7`) then ran the source probe before any translation was submitted.

That immediate probe returned `source_unavailable`. The driver correctly stopped before translation or queue completion. A later read-only probe sent to the **same worker conversation** returned both exact hidden probe values successfully, proving that ChatGPT Project Source listing can become durable before the provider's model-retrieval index is ready.

This exposed a retry-cache flaw: the source-probe operation id had been deterministic only by work/chunk/source revision, so a completed transient `source_unavailable` answer would be replayed forever. Translation operations must never be retried this way, but source probes are read-only and safe to retry.

### Index-readiness fix
- Source probes now have a bounded series of stable per-attempt operation ids.
- Only an explicit `{status: source_unavailable, work_id: <same work>}` is retryable.
- Each attempt remains resumable after process/transport interruption; a restart reuses the same attempt id rather than duplicating it.
- Malformed answers, wrong work ids, mismatched filenames/probes, worker-target failures and uncertain submissions remain fail-closed and are not laundered into a retry.
- Default policy: up to 6 attempts, 10 seconds between completed unavailable probes.
- Tests now total 19/19 PASS and assert that two transient unavailable responses use three distinct stable attempt ids with bounded sleeps.

## Verdict
PASS for deterministic production-runner integration. Automatic new-work source synchronization is verified live; translation smoke remains pending after the indexing-readiness fix.

## Live production smoke completion
After the bounded source-index retry fix, the exact normal production command was rerun for `haikei-ashita-no-watashi` chunk `0001`. The existing work-specific `worker-30` conversation was reused. Source proof passed, the translation operation completed, strict sentence/glossary validation passed, and the queue committed the chunk exactly once. The work is now 1/3 complete.

No manual Project upload, general chat, local-worker fallback, API fallback or manual queue completion was used. The first failed probe had not submitted translation, so the successful run did not duplicate model translation work.

The smoke also exposed stale public projections: workspace state was correct while `work-registry.json` and `work-index.json` still reflected pre-translation status. `refresh_automation_status.py` now projects canonical workspace translation state (`status`, `chunks_done`, `chunks_total`) back into the registry with workspace path fencing, and standard queue completion rebuilds the work index immediately afterward. Existing Beni state is thereby repaired without a special migration. Work-index rows now carry the same chunk progress.

Final verified projection after refresh:
- `beni-death-gamer`: `translation_complete`, 2/2;
- `haikei-ashita-no-watashi`: `translation_pending`, 1/3;
- aggregate: 3 completed chunks, 7 pending chunks.

Regression suite after the projection change: **21/21 PASS**, `git diff --check` PASS.

## Final verdict
PASS for Priority 4. A previously unseen work now flows through automatic immutable Project Source sync, provider indexing readiness, exact Project worker reuse, fresh source proof, real translation, validation, transactional completion and public status/index projection. Daily scheduling remains intentionally disabled until search criteria and an exact Asia/Seoul time are supplied.

## Local-source transport follow-up
The translation task transport was tightened after the production smoke. `source_pipeline.py` already persisted the complete private chunk task under `translation/tasks/<chunk>.json`, so duplicating `source_ja` and `source_segments` into the WebGPT chat was unnecessary.

The production driver now validates that local task against canonical `ja.txt`, sends only an absolute workspace-fenced path plus SHA-256, and requires the Project worker to use Chat On Steroids Core `read` on that exact path. `project_backend.py` rejects references outside `workspace/`, references outside a `translation/tasks/` directory, cross-work/chunk references, changed file hashes and task files without a valid local probe. Other local tools and all local writes remain forbidden. Project Source probes continue to forbid every local tool so they still prove provider-side Project Source retrieval independently.

`source_pipeline.py` now stores a stable random `local_source_probe` in the private task JSON. It is intentionally absent from the chat payload and reused only while the canonical chunk hash is unchanged. `translate_project.py` rejects the result with `LOCAL_SOURCE_PROOF_MISMATCH` unless the worker returns that exact hidden value.

Live transport smoke on the installed runtime used Project worker `worker-32`, conversation `6a9e5a0f-8928-83ee-8d3f-0020b2d1394a`. The recorder captured exactly one local tool call: Core `read` of `/Volumes/DevDrive/Projects/fieldnotes/workspace/automation-runs/local-read-e2e/translation/tasks/0001.json`. The worker then returned the hidden probe and the local harness printed `LOCAL_READ_E2E_OK`. No exec, patch, write, agents or second local-path call was recorded. Fieldnotes regression tests are **23/23 PASS**.

A follow-up attempt to commit a real `sakasano-chagasa` chunk was stopped by the Core write/exec safety gate before the production script ran, so this follow-up changes no real translation progress. The transport itself is live-verified; the existing production translation state remains unchanged.

## Candidate-set production E2E
The full pending candidate queue was then exercised against the installed runtime rather than a fixture. This exposed and repaired four production-only failure modes without enabling any fallback:

1. Routine Project Source synchronization attempted to rewrite an already non-empty Project Instructions field and correctly hit `PROJECT_INSTRUCTIONS_CONFLICT`. Instructions are now setup state, not per-chunk mutation state.
2. Reused sleeping workers exposed their previous answer briefly after a new message was queued. `ProjectBackend` now persists the pre-submit answer hash and waits for a genuinely new answer instead of raising `RESULT_OPERATION_MISMATCH`.
3. Fresh Project worker creation can fail definitively before ChatGPT assigns a conversation. That is now classified as `PROJECT_WORKER_BOOTSTRAP_FAILED`; only this proven pre-send case is retryable. Historical generic failed states are reclassified only when the broker proves the exact worker generation has no conversation id.
4. One complete long translation returned valid JSON followed by one extra closing brace. `parse_envelope` now repairs only that unambiguous trailing-brace case; prose, multiple objects and incomplete JSON remain rejected.

Dynamic per-work Project Source upload was also removed from the translation critical path. `GLOBAL_CONTEXT_v0002_51b585403825.md` had already been UI-listed and was freshly retrieved by each real worker using its hidden source probe. The private local task now includes work metadata and glossary, so current work context is available without a second provider upload.

Live results:
- `deathgame-jikketsu`: **1/1 complete**, Project worker local-read proof passed, output ZIP generated.
- `redo`: **2/2 complete**, both chunks passed fresh Project proof + exact local read; the second chunk reused a complete model answer after narrow JSON-tail repair rather than retranslating it.
- `haikei-ashita-no-watashi`: **3/3 complete**, remaining chunks reused the original work-specific Project conversation and generated the final ZIP.
- `beni-death-gamer`: remains **2/2 complete** from the earlier production smoke.
- `sakasano-chagasa`: **0/2 pending**. The OS reports `CGSSessionScreenIsLocked=Yes`; six bounded fresh-worker attempts all ended before conversation creation with `PROJECT_WORKER_BOOTSTRAP_FAILED`. No model task ran and nothing was committed for this work.

After these fixes the Fieldnotes regression suite is **28/28 PASS** and `git diff --check` passes. Public projection reports **8 completed chunks / 2 pending chunks**. `runtime_sync.py push` copied the completed private artifacts into `~/HermesWorkspace/project/fieldnotes-runtime`; the live private console inventory exposes `ko.txt`, alternating JA/KO, parallel view and ZIP artifacts for Beni, Deathgame, Redo and Haikei. A real `/fieldnotes/api/download` of `redo-translation.zip` returned 94,746 bytes and matched the runtime-mirror SHA-256 exactly.

## Cross-work Project translator pool
The remaining `sakasano-chagasa` blocker demonstrated that binding one Project chat permanently to one work would make every unseen work depend on a fresh browser bootstrap. That is unnecessary after work-specific metadata, glossary, adjacent context and chapter text moved into the exact local task JSON.

`ProjectBackend` now serializes translator use at the Project/role level and reuses the newest sleeping, revivable worker whose Project alias/name/url and role match, even when that worker's original `projectTarget.workId` belongs to another work. The current turn's `response_contract.work_id` and `task.work_id` are explicitly authoritative. Operation state remains per-work, local task path/hash/probe validation remains per-work/chunk, and the global Project-source proof is still fresh on every chunk. Concurrent works cannot race for the same pooled chat because the role pool has its own single-writer lock.

Live verification was performed without unlocking the Mac. `sakasano-chagasa` selected existing `worker-34` / conversation `6a9e62f6-caf0-83e8-bc0c-006f3254bbf8`, whose original Project target was `redo`. No fresh worker was created. The fresh source probe completed through that reused chat, followed by chunk `0001` and chunk `0002`; both passed exact local-read proof, Project-source proof, validation and transactional completion. The final ZIP was generated and mirrored into the private runtime.

Final candidate projection: **10 completed chunks / 0 pending chunks** across all five works. Regression suite: **29/29 PASS**, `git diff --check` PASS, repository validator PASS, and the `sakasano-chagasa` output ZIP passes `unzip -t`.
