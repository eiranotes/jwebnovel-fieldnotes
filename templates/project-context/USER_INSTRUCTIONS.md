# Fieldnotes operator instructions

These are operator-level constraints for this translation workflow.

1. Keep one shared ChatGPT Project, Fieldnotes. Do not create a separate Project
   for each novel.
2. Keep exactly one translation conversation per novel. All later chunks for the
   same novel continue in that conversation so its translation context stays
   coherent. Never use another novel's conversation or glossary as evidence.
3. Work-specific source, metadata, glossary and adjacent context come from the
   exact local task JSON for that novel, not from a newly uploaded per-work
   Project Source.
4. If the current task/glossary contains a newer explicit correction, follow that
   correction over an older conversational assumption and keep the correction
   consistent in later chunks.
5. The external Fieldnotes driver owns validation, output naming, packaging and
   local writes. The model returns only the requested result contract.
