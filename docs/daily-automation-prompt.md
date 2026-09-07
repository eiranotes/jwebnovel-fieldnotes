# Daily ChatGPT/Steroids Job Contract

You are executing the daily Japanese web-novel research pipeline in repository:
`/Volumes/DevDrive/Projects/fieldnotes`.

Use Chat On Steroids Core for all repository reads/writes, state mutation, git operations and validation. Use current web search for discovery. Body acquisition is performed only by the repository's private local acquisition routes; never publish source or translated fulltext to GitHub Pages.

For this run:

1. Import phone/private-console state first with `python3 scripts/runtime_sync.py pull`. The runtime mirror is not a Git repository; the canonical repository remains `/Volumes/DevDrive/Projects/fieldnotes`.
2. Start a run log with `python3 scripts/automation_log.py --task daily_discovery --action run --status started ...` and keep the same run id for the daily discovery steps.
3. Read `config/automation.json`, `config/search-profiles.json`, `docs/search-protocol.md`, `data/automation-status.json`, and rebuild the persistent seen index with `python3 scripts/rebuild_work_index.py`. If `workspace/preference-model.json` exists, read it as a private local soft-ranking prior.
4. Select the search groups for this run with `python3 scripts/select_search_profiles.py --commit`. If the page explicitly selected more than one group, run every selected group separately. If none is selected, obey `selection.when_none` (`round_robin`, `least_recently_run`, `random_daily`, or `all_enabled`) and `rotation_batch_size`.
5. If no enabled profile is available, update status/logs, run `python3 scripts/runtime_sync.py push`, and stop without inventing criteria.
6. For each selected search profile, create one dated research entry. Same date can have multiple entries; assign next `YYYY-MM-DD-NN`.
7. Discover fresh candidates with current web/platform metadata. Apply that profile's constraints and default 300,000-char threshold. Keep sub-300k only as explicit high-fit length exceptions. After hard filters and request-specific fingerprinting, use the selected profile's `learned_preferences`, private preference signals, and positive/negative feedback examples only as secondary ranking evidence. Never let learned taste override explicit current-request criteria.
8. Before sampling/ranking, compare the harvested candidate list against `data/work-index.json` or batch it through `python3 scripts/work_index.py --unseen-only`. In strict mode, do not re-surface works already present in the index. Cross-posts are canonicalized by normalized title + author when available.
9. Read enough actual accessible sample text to assess the profile-specific fingerprint. Do not rank based on tags/synopsis alone.
10. Persist shortlist, rejected/deferred candidates, evidence, checked date, and paths. Rebuild `data/work-index.json` after each completed entry and update the archive.
11. Run `scripts/full_pipeline.py --entry ENTRY_ID --top-n N --episodes 5`. It registers targets, acquires the first five public reader episodes into the private local workspace, prepares merged source, creates the resumable chunk queue, seeds ruby/glossary evidence, and updates status. Reuse existing acquisition manifests unless a refresh is needed.
12. If automatic acquisition fails for a work, retain the manual `source_inbox/` fallback and record the blocker instead of discarding the candidate.
13. Use the verified Project backend for translation. `python3 scripts/translate_project.py --max-chunks N` owns queue selection, immutable Project Source synchronization, hidden source-retrieval proof, exact Project/work worker reuse, strict sentence/glossary validation, and transactional completion. Do not manually translate a queue task or bypass this driver with a general chat/local worker/API fallback.
14. The Project driver must stay fail-closed: `backend=webgpt_project`, `activation=verified_live`, `require_source_probe=true`, and `allow_fallback=false`. If source synchronization, Project membership, source proof, worker identity, validation or result recovery is uncertain, record the blocker and do not resubmit/complete by hand.
15. Continue only up to the configured daily translation cap. If no cap is configured, bound the run to one Project translation chunk at a time; later runs resume the queue durably rather than submitting duplicate work.
16. Run `scripts/refresh_automation_status.py`, `scripts/rebuild_work_index.py`, and `scripts/validate_repo.py`.
17. Finish the run log with done/partial/error status. Commit only public metadata/docs/code/state, never source or translated fulltext. Push main and verify GitHub Pages responds successfully.
18. The private `taste.html` daily review deck is derived only from that date's `shortlist` and `length_exceptions`. Do not include rejected/deprioritized works. It uses the local acquired sample so the user can read and answer from iPhone without publishing source text.
19. Refresh the internal private runtime with `python3 scripts/runtime_sync.py push` so the iPhone daily taste page and operations console see the newest entries, local samples, profile state, queues, artifacts, feedback model and logs.
20. Report: selected search groups, new entries, duplicates filtered, shortlist count, daily taste deck count, full-translation progress, translated chunks, blockers.
