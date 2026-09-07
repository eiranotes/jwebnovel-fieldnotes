# Priority 2 Fieldnotes Project translation

## Scope
Build the fail-closed Fieldnotes translation backend around a verified ChatGPT Project, immutable Project Sources, reusable per-work workers, strict segment validation and restart-safe completion.

## Starting State
The existing translation queue could prepare Japanese chunks and merge/save model results but had no Project-only execution boundary, no proof that the model actually retrieved the intended Project Sources, and completion could partially update output/glossary state if interrupted.

## Findings
A Project route alone is not sufficient evidence that a worker used the correct source files. The local repository must remain authoritative; Project files are immutable published snapshots. Model access therefore needs an unprompted retrieval proof that is generated inside each uploaded source and never copied into the model task.

Worker submission also has an ambiguity boundary: a lost successful HTTP response may have created a real chat. Retrying automatically could duplicate translation. Accepted operations must be durable and resumable by exact worker generation instead.

## Root Cause / Architecture Decision
- Local Fieldnotes state is canonical.
- Project Sources contain stable/semi-stable context only; current chapter chunks stay in the task payload.
- `webgpt_project` is fail-closed: no silent general-chat, local-worker or API fallback.
- Each source snapshot carries a random retrieval probe. Tasks know the exact filename/revision/hash but not the probe value. Translation proceeds only after the Project worker returns the values read from those files.
- Workers are reused only for the same Project/work/role target.
- Chunk completion is journaled and idempotent before glossary/manifest/output mutation.

## Changes
- `scripts/automation_store.py`: durable atomic files, nonblocking single-writer locks and bounded workspace path enforcement.
- `scripts/project_context.py`: immutable `GLOBAL_CONTEXT` and `WORK_<work_id>` snapshots with versions, hashes and hidden retrieval probes.
- `scripts/project_backend.py`: Project-only Steroids bridge client, exact worker reuse, durable operation state and uncertainty fencing.
- `scripts/project_sources.py`: Project Source synchronization request with UI receipt validation; source listing is not treated as retrieval proof.
- `scripts/translate_project.py`: source probe, translation request, strict result validation and queue completion without fallback.
- `scripts/source_pipeline.py`: strict ordered segment checks, source hashes, glossary conflict validation and transactional chunk completion.
- `scripts/translation_queue.py`: captures status-refresh subprocess output so machine-readable completion output remains valid JSON.
- `config/project-translation.json`: Project-only activation policy.
- `templates/project-context/*`: Project Instructions and common context contract.
- `tests/*`: backend, context, translation commit and two-chunk integration coverage.

## Files Changed
`.gitignore`, `config/project-translation.json`, `scripts/automation_store.py`, `scripts/project_backend.py`, `scripts/project_context.py`, `scripts/project_sources.py`, `scripts/translate_project.py`, `scripts/source_pipeline.py`, `scripts/translation_queue.py`, `templates/project-context/*`, `tests/*`.

## Tests
`python3 -m unittest discover -s tests -v`: 17/17 PASS.
`git diff --check`: PASS.
The two-chunk integration test is deterministic and uses a fake Project transport. It validates routing/commit semantics but is not claimed as a real provider translation.

## Actual E2E
The real `Fieldnotes` ChatGPT Project was created and registered by the Steroids Project routing layer. The Project translation driver is wired to that alias and refuses unknown/unverified targets. Real Project Source upload/retrieval and Beni translation remain the next live gate.

## Known Limitations
The actual Project currently has no verified uploaded context sources from this driver. Project Instructions have not yet been verified saved. No production translation has been accepted through source-probe verification yet.

## Remaining Blockers
1. Synchronize `GLOBAL_CONTEXT` and `WORK_beni-death-gamer` to the real Project.
2. Verify instructions/source listing using the browser-owned UI receipt.
3. Verify the hidden source probes through a real Project worker.
4. Process Beni chunks `0001` and `0002` through the same reusable worker.
5. Only then change activation from blocked to live and continue Priority 3/4.

## Commit(s)
This implementation is committed as the Priority 2 deterministic checkpoint before the real Project Source mutation.

## Verdict
PARTIAL. Deterministic Project translation architecture and safety properties pass; live Project Source-backed translation is not yet proven.
