from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from novelpipeline.config import load_config
from novelpipeline.db import StateDB
from novelpipeline.models import WorkCandidate
from novelpipeline.sites.common import soup, text_with_ruby
from novelpipeline.translate import WorkTranslator, chunk_text


class CoreTests(unittest.TestCase):
    def test_ruby_is_preserved(self):
        doc = soup("<div><p>九条<ruby>玲奈<rp>(</rp><rt>れいな</rt><rp>)</rp></ruby>です。</p></div>")
        text, pairs = text_with_ruby(doc.div)
        self.assertIn("玲奈《れいな》", text)
        self.assertNotIn("()", text)
        self.assertIn(("玲奈", "れいな"), pairs)

    def test_chunker_respects_limit_for_normal_paragraphs(self):
        text = "\n\n".join(["あ" * 400 for _ in range(10)])
        chunks = chunk_text(text, 1000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(x) <= 1000 for x in chunks))

    def test_db_candidate_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = StateDB(Path(tmp) / "state.sqlite3")
            item = WorkCandidate(site="narou", work_id="n1234ab", url="https://ncode.syosetu.com/n1234ab/")
            self.assertTrue(db.upsert_candidate(item))
            self.assertFalse(db.upsert_candidate(item))
            rows = db.list_works()
            self.assertEqual(len(rows), 1)

    def test_example_config_loads(self):
        root = Path(__file__).resolve().parents[1]
        config = load_config(root / "config.example.toml")
        self.assertEqual(config.pipeline.episodes_per_work, 5)
        self.assertFalse(config.translation.enabled)

    def test_translation_resume_reuses_completed_chunks(self):
        class FakeProvider:
            def __init__(self):
                self.calls = 0

            def translate(self, *, source, metadata, glossary, previous_context):
                self.calls += 1
                return {
                    "translation": "번역:" + source,
                    "glossary_updates": [
                        {"original": "玲奈", "reading": "れいな", "ko": "레이나", "type": "person"}
                    ],
                }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_path = root / "config.toml"
            cfg_path.write_text(
                """
[pipeline]
data_dir = "data"
site_dir = "site"
log_dir = "logs"
episodes_per_work = 5
max_new_works_per_run = 10
request_delay_seconds = 0
request_timeout_seconds = 30
user_agent = "test"

[translation]
enabled = true
provider = "openai_compatible"
model_env = "OPENAI_MODEL"
api_key_env = "OPENAI_API_KEY"
base_url_env = "OPENAI_BASE_URL"
chunk_chars = 1000
previous_context_chars = 100
temperature = 0.2

[seeds]
urls = []
""".strip()
                + "\n",
                encoding="utf-8",
            )
            config = load_config(cfg_path)
            db = StateDB(config.pipeline.data_dir / "state.sqlite3")
            db.upsert_candidate(
                WorkCandidate(
                    site="narou",
                    work_id="n1234ab",
                    url="https://ncode.syosetu.com/n1234ab/",
                )
            )
            db.update_work("narou", "n1234ab", status="DOWNLOADED")

            work = config.pipeline.data_dir / "works" / "narou" / "n1234ab"
            (work / "merged").mkdir(parents=True, exist_ok=True)
            (work / "metadata.json").write_text(
                json.dumps(
                    {
                        "site": "narou",
                        "work_id": "n1234ab",
                        "url": "https://ncode.syosetu.com/n1234ab/",
                        "title": "테스트",
                        "author": "작가",
                        "summary": "",
                        "episode_urls": [
                            f"https://ncode.syosetu.com/n1234ab/{i}/" for i in range(1, 6)
                        ],
                        "extra": {},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (work / "glossary.json").write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "original": "玲奈",
                                "reading": "れいな",
                                "ko": "",
                                "type": "ruby_hint",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (work / "merged" / "original_001-005.txt").write_text(
                ("玲奈《れいな》です。\n\n" * 120).strip() + "\n",
                encoding="utf-8",
            )

            provider = FakeProvider()
            translator = WorkTranslator(config, db, provider=provider)
            translator.translate_work("narou", "n1234ab")
            first_calls = provider.calls
            self.assertGreater(first_calls, 1)
            translator.translate_work("narou", "n1234ab")
            self.assertEqual(provider.calls, first_calls)

            glossary = json.loads((work / "glossary.json").read_text(encoding="utf-8"))
            self.assertEqual(glossary["entries"][0]["ko"], "레이나")
            self.assertTrue((work / "bilingual" / "ja-ko_001-005.md").exists())


if __name__ == "__main__":
    unittest.main()
