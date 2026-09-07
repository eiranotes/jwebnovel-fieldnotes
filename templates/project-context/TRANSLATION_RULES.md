# Fieldnotes general Japanese-to-Korean fiction translation rules

Translate fiction into natural Korean while preserving the original meaning,
voice, scene temperature, point of view, register and paragraph membership.
Do not summarize, embellish, censor, explain or silently omit source content.

The local task contains stable sentence ids. Return exactly one Korean row for
every sentence segment in the original order. Never merge, split, add or skip
sentence ids. Metadata segments are context only and are not translation rows.

Use the current work's established Korean spellings when present. For a new
proper name, prefer explicit ruby/furigana and work metadata over an unsupported
guess. Ruby may express wordplay, emphasis or an alternate reading; do not
mechanically replace the written expression with an unrelated pronunciation.
Record uncertain terminology/name decisions in glossary_update rather than
silently making them global rules.

Dialogue, narration, honorific distance and character-specific speech should read
naturally in Korean without flattening meaningful distinctions. Preserve unusual
or dry phrasing when it is part of the work's voice instead of normalizing every
line into generic polished prose.
