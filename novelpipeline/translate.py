from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

from .config import AppConfig
from .db import StateDB
from .download import work_dir, write_json, write_state


def chunk_text(text: str, max_chars: int) -> list[str]:
    max_chars = max(1000, max_chars)
    paragraphs = re.split(r"\n{2,}", text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            for start in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[start : start + max_chars])
            continue
        addition = len(paragraph) + (2 if current else 0)
        if current and current_len + addition > max_chars:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len += addition
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _extract_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
        raise


class OpenAICompatibleProvider:
    def __init__(self, config: AppConfig):
        t = config.translation
        self.api_key = os.environ.get(t.api_key_env, "").strip()
        self.base_url = os.environ.get(t.base_url_env, "https://api.openai.com/v1").strip().rstrip("/")
        self.model = os.environ.get(t.model_env, "").strip()
        self.temperature = t.temperature
        if not self.api_key:
            raise RuntimeError(f"Missing translation API key env: {t.api_key_env}")
        if not self.model:
            raise RuntimeError(f"Missing translation model env: {t.model_env}")

    def translate(self, *, source: str, metadata: dict, glossary: dict, previous_context: str) -> dict:
        system = (
            "일본어 웹소설을 자연스러운 한국어 소설문으로 정확하게 번역한다. "
            "내용을 요약/생략/추가하지 말고 문단과 대화 구분을 보존한다. "
            "인명·지명·고유명사는 제공된 루비와 glossary를 우선한다. "
            "이미 glossary에 ko가 있는 항목은 반드시 같은 표기를 사용한다. "
            "새 고유명사에 확실한 한국어 표기가 생기면 glossary_updates에 기록한다. "
            "응답은 설명 없이 JSON 객체만 출력한다: "
            '{"translation":"...","glossary_updates":[{"original":"...","reading":"...","ko":"...","type":"person|place|term"}]}.'
        )
        glossary_entries = glossary.get("entries", [])[-500:]
        user_payload = {
            "work": {
                "title": metadata.get("title", ""),
                "author": metadata.get("author", ""),
                "summary": metadata.get("summary", ""),
            },
            "glossary": glossary_entries,
            "previous_translation_tail": previous_context,
            "source": source,
        }
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "novel-daily-pipeline/0.1",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as res:
            payload = json.loads(res.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        if not isinstance(parsed.get("translation"), str) or not parsed["translation"].strip():
            raise ValueError("Translator response has no translation text")
        if not isinstance(parsed.get("glossary_updates", []), list):
            parsed["glossary_updates"] = []
        return parsed


def merge_glossary(glossary: dict, updates: list[dict]) -> None:
    entries = glossary.setdefault("entries", [])
    by_original = {str(x.get("original", "")): x for x in entries if x.get("original")}
    for update in updates:
        original = str(update.get("original", "")).strip()
        ko = str(update.get("ko", "")).strip()
        if not original or not ko:
            continue
        current = by_original.get(original)
        if current:
            current["ko"] = ko
            if update.get("reading"):
                current["reading"] = str(update["reading"])
            if update.get("type"):
                current["type"] = str(update["type"])
        else:
            item = {
                "original": original,
                "reading": str(update.get("reading", "")),
                "ko": ko,
                "type": str(update.get("type", "term")),
            }
            entries.append(item)
            by_original[original] = item


class WorkTranslator:
    def __init__(self, config: AppConfig, db: StateDB, provider=None):
        self.config = config
        self.db = db
        if provider is not None:
            self.provider = provider
        else:
            if config.translation.provider != "openai_compatible":
                raise ValueError(f"Unsupported translation provider: {config.translation.provider}")
            self.provider = OpenAICompatibleProvider(config)

    def translate_work(self, site: str, work_id: str) -> None:
        root = work_dir(self.config, site, work_id)
        metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
        glossary_path = root / "glossary.json"
        glossary = json.loads(glossary_path.read_text(encoding="utf-8")) if glossary_path.exists() else {"entries": []}
        merged_files = sorted((root / "merged").glob("original_*.txt"))
        if not merged_files:
            raise FileNotFoundError(f"Merged source missing for {site}/{work_id}")
        source_text = merged_files[-1].read_text(encoding="utf-8")
        chunks = chunk_text(source_text, self.config.translation.chunk_chars)

        chunk_dir = root / "chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        translations: list[str] = []
        bilingual_parts: list[str] = []
        self.db.update_work(site, work_id, status="TRANSLATING", last_error=None)
        write_state(root / "state.json", status="TRANSLATING", extra={"translation_chunks": len(chunks)})

        previous = ""
        for index, source in enumerate(chunks, start=1):
            source_path = chunk_dir / f"{index:04d}.source.txt"
            trans_path = chunk_dir / f"{index:04d}.translation.txt"
            meta_path = chunk_dir / f"{index:04d}.json"
            source_path.write_text(source.rstrip() + "\n", encoding="utf-8")
            digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
            old = self.db.get_chunk(site, work_id, index)
            if old and old["status"] == "DONE" and old["source_sha256"] == digest and trans_path.exists():
                translated = trans_path.read_text(encoding="utf-8").strip()
            else:
                try:
                    result = self.provider.translate(
                        source=source,
                        metadata=metadata,
                        glossary=glossary,
                        previous_context=previous[-self.config.translation.previous_context_chars :],
                    )
                    translated = result["translation"].strip()
                    merge_glossary(glossary, result.get("glossary_updates", []))
                    write_json(glossary_path, glossary)
                    trans_path.write_text(translated.rstrip() + "\n", encoding="utf-8")
                    write_json(
                        meta_path,
                        {
                            "chunk_no": index,
                            "source_sha256": digest,
                            "glossary_updates": result.get("glossary_updates", []),
                        },
                    )
                    self.db.upsert_chunk(
                        site=site,
                        work_id=work_id,
                        chunk_no=index,
                        source_sha256=digest,
                        source_path=str(source_path.resolve()),
                        translation_path=str(trans_path.resolve()),
                        status="DONE",
                    )
                except Exception as exc:
                    self.db.upsert_chunk(
                        site=site,
                        work_id=work_id,
                        chunk_no=index,
                        source_sha256=digest,
                        source_path=str(source_path.resolve()),
                        translation_path=None,
                        status="ERROR",
                        error=str(exc),
                    )
                    raise
            translations.append(translated)
            bilingual_parts.append(
                f"## Chunk {index:04d}\n\n### 원문\n\n{source.strip()}\n\n### 번역\n\n{translated}"
            )
            previous = translated

        translated_dir = root / "translated"
        bilingual_dir = root / "bilingual"
        translated_dir.mkdir(parents=True, exist_ok=True)
        bilingual_dir.mkdir(parents=True, exist_ok=True)
        suffix = f"001-{min(self.config.pipeline.episodes_per_work, int(metadata.get('episode_urls') and len(metadata['episode_urls']) or 1)):03d}"
        (translated_dir / f"ko_{suffix}.txt").write_text("\n\n".join(translations).rstrip() + "\n", encoding="utf-8")
        (bilingual_dir / f"ja-ko_{suffix}.md").write_text("\n\n---\n\n".join(bilingual_parts).rstrip() + "\n", encoding="utf-8")
        self.db.update_work(site, work_id, status="TRANSLATED", last_error=None)
        write_state(root / "state.json", status="TRANSLATED", extra={"translation_chunks": len(chunks)})
