# 2026-09-08 Translation Transport Hardening

## Scope

This work hardened the Fieldnotes Project-translation path after repeated browser-worker failures on the 2026-09-08 queue. The production invariant remains **one Fieldnotes Project, one Project conversation per work, sequential chunks inside that conversation**. Copyrighted source stays in the exact local task JSON; the model may read that one file only.

## Final production path

```text
translation/tasks/<chunk>.json
  -> Project worker reads the exact hash-validated task with Core read
  -> worker returns one JSON response envelope in the same Project conversation
  -> ProjectBackend validates operation/work envelope identity
  -> trusted Fieldnotes backend creates
     workspace/automation-runs/backend/<work>/<role>/<operation>.worker-result.json
     with exclusive-create semantics as a transport receipt
  -> translation driver validates Project Source proof + local_source_proof
     + exact sentence-id/order alignment + glossary structure
  -> transactional chunk commit
  -> final private TXT / JA-KO / ZIP artifacts
  -> exact worker conversation tab cleanup after result capture
```

The model **does not write local files**. `*.worker-result.json` is a driver-created durable **transport receipt**, not a model-created translation file and not proof by itself that the translation passed the semantic validator. An existing identical receipt is accepted as idempotent crash recovery; conflicting existing content is a hard failure. Canonical chunk completion still requires the downstream Project/local proof, segment-order and glossary checks.

## Incidents and resolutions

| Symptom | Root cause | Resolution | Verification |
|---|---|---|---|
| Primary translation repeatedly failed before any translation result existed | Project worker bootstrap/send path was failing; later retries inherited the generated draft and treated it as user text | Fresh bootstrap handling was hardened in Steroids; exact generated stale drafts are distinguishable from trusted user text; post-send uncertainty remains fail-closed | Prior Steroids regression and live Project bootstrap verification |
| Codex fallback added a second failure (`503 No usable credential for group fieldnotes`) | The local Codex account pool had no usable quota/credential | Automatic translation fallback is disabled. Primary Project transport either succeeds or leaves a durable blocked state | Fieldnotes integration test asserts disabled fallback never calls Codex |
| A work with a long Japanese title failed immediately at spawn | Steroids broker labels have a 60-character limit; Fieldnotes used the full conversation title as the broker label | Broker label is truncated to 60 characters while the full requested conversation title remains in task/mapping metadata | `test_long_conversation_title_is_shortened_only_for_broker_label` |
| Project Instructions update failed with `PROJECT_INSTRUCTIONS_CONFLICT` | The UI safety rule correctly refused to overwrite a non-empty existing provider value, but there was no supported migration path | Project Instructions now use compare-and-swap. Replacement is allowed only when the live textarea exactly equals the last provider-verified value; a tracked baseline exists only to bootstrap the first migration | Live CAS update succeeded; Steroids Project UI tests remain green |
| Direct model write experiment stalled or returned chat JSON instead of a file | Generic write tools introduce approval/tool-lifetime uncertainty and conflicted with the higher-level read-only Project policy; closing the tab also interrupts local tool execution/recording | Abandoned model-side writes. The worker is read-only and returns one result envelope; the trusted driver creates the operation result receipt locally | `narou-n6584ll/0003` completed with `result_source=driver_capture` and a create-only result receipt |
| Closing a worker tab immediately after conversation bind did not safely complete local-tool work | A bound provider turn can continue remotely, but Steroids still needs the page lifetime for local Core calls and final transcript/answer capture | Do not close on send/bind. Keep the exact worker page until the final answer is captured and the local result/commit succeeds; then close that exact conversation tab | `narou-n6584ll/0003` completion reported exact tab cleanup after commit |
| Reused worker could expose the previous chunk's final answer while the new wake was still starting | Sleeping worker status retains the previous completed answer | Persist `answer_before_submit_sha256` and reject that exact answer until a new answer appears. This guard runs before result-path interpretation | Reuse/old-answer regression tests pass |
| `narou-n6584ll/0003` timed out after an accepted send and could not be safely resent | Timeout is not evidence that provider work stopped; resubmission could duplicate a model turn | Added exact remote-interrupt recovery. Steroids must prove `worker id + createdAt + bound conversation`, click ChatGPT Stop, prove generation ended, persist the receipt, then Fieldnotes marks the operation `interrupted` and may revive the same conversation | Live `remoteStopped:true`; worker moved to `sleeping/revivable`; same operation reused worker-82 and the same conversation; chunk completed 327/327 sentence rows |
| Same-conversation revival sat in `leased` with no progress | An older stale automation-marked tab and the new revival tab both existed for the same conversation | The stale exact marker tab was removed; new interrupt-marked helper tabs now close after a committed interrupt receipt. Normal revival continues to prefer the exact existing worker tab | Live 0003 wake moved from `waking` to `active`, pending/awaitingAck returned to zero |
| A first implementation of result-file delivery checked a reused worker too early | Previous `complete=true` answer was interpreted before the old-answer hash fence | Old-answer identity check is applied before any result receipt or chat-response interpretation | Project backend reuse tests pass |
| Runtime sync reported a two-sided `data/automation-logs.json` conflict during canonical cleanup | Canonical had three new translation-completion records while the private runtime had nine newer taste-response records, both diverged from the last sync hash | Did not choose by mtime or overwrite either side. Merged entries by exact JSON identity, preserved both sets in timestamp order, wrote the identical merged log to canonical/runtime, then reran hash-based sync | Second `runtime_sync.py push` returned `status=pushed`, preserved runtime with no conflicts |

## Exact timeout recovery contract

A `WORKER_RESULT_TIMEOUT` does **not** authorize retry. Safe retry requires all of the following:

1. The operation is still `accepted` and has the exact `worker_id` and `created_at` generation.
2. Steroids recovery resolves that exact worker to one bound conversation.
3. A marked exact-conversation interrupt page observes/clicks ChatGPT's own Stop control.
4. The page proves generation ended without changing conversation.
5. Steroids durably records a committed interrupt receipt and returns `remoteStopped:true`.
6. Only then may Fieldnotes persist `state=interrupted` for that operation.
7. The next execution reuses the same sleeping/revivable Project worker and same conversation.

If any proof is missing, the operation remains blocked. `cancel` is not equivalent: it withdraws local automation authority but does not prove a provider turn stopped.

## Project Instructions ownership

Project Source files are immutable revisions, but Project Instructions are mutable provider state. Their update rule is now:

- empty provider instructions -> safe initial write;
- non-empty value equal to the exact last verified provider value -> compare-and-swap update allowed;
- any other non-empty value -> `PROJECT_INSTRUCTIONS_CONFLICT`, no overwrite.

`templates/project-context/PROJECT_INSTRUCTIONS_BASELINE.md` is an exact historical provider value used only when migrating an installation that predates the private provider-state receipt. After a successful CAS, ignored `workspace/project-context/provider-project-instructions.json` is authoritative for the next expected value. **Do not edit the baseline as prose documentation.**

## Live E2E evidence

`narou-n6584ll`, chunk `0003`:

- original operation: same durable operation id retained in private backend state;
- existing worker: `worker-82`;
- existing Project conversation: exact id retained in private broker/backend state;
- exact remote interrupt returned `remoteStopped:true`;
- worker became `sleeping`, `revivable=true`;
- retry reused the same worker/conversation (`reused=true`), not a new chat;
- response contained 327 sentence translations;
- driver created the operation-specific `*.worker-result.json` receipt;
- operation completed with `result_source=driver_capture`;
- work reached `translation_complete`, 3/3 chunks;
- output builder emitted `ko.txt`, `ja-ko.md`, title-based translation TXT, and ZIP;
- output format contained no `원문:` / `번역:` labels;
- exact worker tab cleanup closed one finished tab after completion.

## Remaining operational risks

- ChatGPT DOM/UI changes can invalidate Project settings selectors or the Stop-button proof. These paths must fail closed rather than assume success.
- A legacy stale automation-marked tab can still interfere with revival routing until it is positively identified; never close arbitrary user tabs by title alone.
- Provider-side conversation title rename is presentation-only and remains separate from work identity; `(Project, work_id, role)` and conversation id are the authority.
- Codex fallback is intentionally unavailable/disabled; primary transport failures should remain visible instead of silently switching providers.
- Current queue state after this E2E is 4 pending works / 9 pending chunks. Those are ordinary backlog, not failed `narou-n6584ll` work.

## Regression gates

Before changing this path again, require at minimum:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
git diff --check
```

For browser/interrupt changes also require the Steroids bridge/content/extension suite, TypeScript typecheck, packaged-app hash verification, and at least one live exact-conversation recovery smoke before claiming the recovery path is operational.
