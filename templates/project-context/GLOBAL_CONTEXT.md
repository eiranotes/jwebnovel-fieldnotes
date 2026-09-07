# Fieldnotes common context

Fieldnotes keeps canonical metadata, source text, versioned translation guides,
glossaries, tasks and checkpoints on the Mac. This Project holds published
workflow/reference snapshots only; it is not the authoritative database.

There is one ChatGPT Project named Fieldnotes. Every novel gets its own Project
conversation and every chunk of that novel continues in that same conversation.
Never reuse a different novel's conversation as translation context. The Project
Sources are application-wide rules shared by those conversations; there is no
per-novel Project and no per-novel Project Source in the production path.

Each Project Source records a content revision and retrieval probe. Returning a
probe demonstrates access to that exact source; it is not itself a translation
quality signal. Private work metadata, Japanese text, sentence ids, adjacent
context, ruby evidence and the current glossary live in the exact local task JSON
named by the current translation task.

Output result:
{"work_id":"current work","chunk_id":"current chunk",
 "segment_translations":[{"id":"original sentence id","ko":"Korean text"}],
 "glossary_update":{"people":{},"places":{},"terms":{},"ruby_notes":{},"decisions":[]}}

The local driver checks ids, duplicate/order/empty rows, identity, source hash
and glossary conflicts before completion. Original and translated full text
remain private. Public status contains only metadata and stage summaries.
