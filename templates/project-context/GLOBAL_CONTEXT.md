# Fieldnotes common context

Fieldnotes keeps canonical metadata, source text, versioned translation guides,
glossaries, tasks and checkpoints on the Mac. This Project holds published
reference snapshots only; it is not the authoritative database.

A work source is named WORK_<work_id>_v<version>_<hash>.md. Use the exact file
named in the task, not a similarly named older upload. Each source records its
content revision and a retrieval probe. A returned probe demonstrates access to
that source content; it is not a guarantee of comprehensive reading or model
translation quality.

The current Japanese chunk, previous tail, following head, source segment ids
and runtime glossary corrections arrive directly in each translation task.
Do not translate adjacent context again. Runtime corrections may be newer than
the published source snapshot and must be respected without inventing a new
Project upload.

Output result:
{"work_id":"current work","chunk_id":"current chunk",
 "segment_translations":[{"id":"original sentence id","ko":"Korean text"}],
 "glossary_update":{"people":{},"places":{},"terms":{},"ruby_notes":{},"decisions":[]}}

The local driver checks ids, duplicate/order/empty rows, identity, source hash
and glossary conflicts before completion. Original and translated full text
remain private. Public status contains only metadata and stage summaries.
