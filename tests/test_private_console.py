import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import private_console
from private_console import _content_disposition


class PrivateConsoleTests(unittest.TestCase):
    def test_unicode_download_name_uses_ascii_safe_rfc5987_header(self):
        value=_content_disposition('逆さの茶笠 - 번역본.txt')
        value.encode('latin-1')
        self.assertIn("filename*=UTF-8''",value)
        self.assertIn('%E9%80%86',value)
        self.assertIn('%EB%B2%88%EC%97%AD%EB%B3%B8.txt',value)

    def test_artifact_inventory_exposes_only_alternating_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            registry=root/'data'/'work-registry.json'
            full_queue=root/'data'/'full-translation-queue.json'
            output=root/'workspace'/'demo'/'translation'/'output'
            output.mkdir(parents=True)
            registry.parent.mkdir(parents=True,exist_ok=True)
            registry.write_text(json.dumps({'works':[{'title':'테스트','work_id':'demo','workspace':'workspace/demo'}]},ensure_ascii=False),encoding='utf-8')
            full_queue.write_text(json.dumps({'requests':[]}),encoding='utf-8')
            (output/'ko.txt').write_text('번역',encoding='utf-8')
            (output/'ja-ko.md').write_text('원문 번역',encoding='utf-8')
            (output/'demo-translation.zip').write_bytes(b'zip')
            alternating=output/'테스트 - 번역본.txt'
            alternating.write_text('원문\n번역',encoding='utf-8')

            previous=(private_console.ROOT,private_console.REGISTRY,private_console.FULL_QUEUE)
            try:
                private_console.ROOT=root
                private_console.REGISTRY=registry
                private_console.FULL_QUEUE=full_queue
                rows=private_console.artifact_inventory()
            finally:
                private_console.ROOT,private_console.REGISTRY,private_console.FULL_QUEUE=previous

            self.assertEqual([row['filename'] for row in rows],['테스트 - 번역본.txt'])
            self.assertEqual(rows[0]['kind'],'alternating_translation')

    def test_taste_sample_reads_alternating_translation_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            entries=root/'data'/'entries'
            registry=root/'data'/'work-registry.json'
            taste_state=root/'workspace'/'daily-taste-state.json'
            output=root/'workspace'/'demo'/'translation'/'output'
            entries.mkdir(parents=True)
            registry.parent.mkdir(parents=True,exist_ok=True)
            output.mkdir(parents=True)
            taste_state.parent.mkdir(parents=True,exist_ok=True)
            (entries/'2026-09-06-01.json').write_text(json.dumps({
                'entry_id':'2026-09-06-01','date':'2026-09-06','results':{'shortlist':[{
                    'title':'테스트','platform':'Narou','url':'https://example.test/work','rank':'A1'
                }]}
            },ensure_ascii=False),encoding='utf-8')
            registry.write_text(json.dumps({'works':[{
                'title':'테스트','work_id':'demo','workspace':'workspace/demo','platform':'Narou','url':'https://example.test/work'
            }]},ensure_ascii=False),encoding='utf-8')
            taste_state.write_text(json.dumps({'responses':[]}),encoding='utf-8')
            (output/'테스트 - 번역본.txt').write_text('原文\n번역\n',encoding='utf-8')

            previous=(private_console.ROOT,private_console.ENTRIES,private_console.REGISTRY,private_console.DAILY_TASTE)
            try:
                private_console.ROOT=root
                private_console.ENTRIES=entries
                private_console.REGISTRY=registry
                private_console.DAILY_TASTE=taste_state
                deck=private_console.taste_deck('2026-09-06')
                sample=private_console.taste_sample('2026-09-06',deck['items'][0]['canonical_key'])
            finally:
                private_console.ROOT,private_console.ENTRIES,private_console.REGISTRY,private_console.DAILY_TASTE=previous

            self.assertEqual(len(deck['items']),1)
            self.assertEqual(sample['reading_mode'],'alternating')
            self.assertEqual(sample['text'],'原文\n번역\n')


if __name__=='__main__':unittest.main()
