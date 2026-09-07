import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from automation_store import AutomationError, atomic_json
from project_context import build_common_packs, public_pack, source_probe_task, verify_source_probe


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        source=Path(__file__).resolve().parents[1]/'templates/project-context'
        destination=self.root/'templates/project-context';destination.mkdir(parents=True)
        for f in source.glob('*.md'):(destination/f.name).write_text(f.read_text())
        self.work=self.root/'workspace/books/example';self.work.mkdir(parents=True)
    def tearDown(self): self.tmp.cleanup()
    def test_stable_revision_and_no_probe_in_prompt(self):
        packs=build_common_packs(self.root)
        self.assertEqual(packs,build_common_packs(self.root))
        self.assertEqual([p['source_name'] for p in packs],['GLOBAL_CONTEXT','WORK_translation_rules','WORK_user_instructions'])
        prompt=source_probe_task('example',*packs,conversation_title='260906-Example')
        for pack in packs:
            self.assertNotIn(pack['source_probe'],json.dumps(prompt))
            self.assertNotIn('source_probe',public_pack(pack))
        self.assertEqual(prompt['conversation_title'],'260906-Example')
    def test_revision_changes_when_user_instructions_change_and_old_file_survives(self):
        before=build_common_packs(self.root)[2]
        path=self.root/'templates/project-context/USER_INSTRUCTIONS.md'
        path.write_text(path.read_text()+'\nnew operator rule\n')
        after=build_common_packs(self.root)[2]
        self.assertEqual(after['context_version'],before['context_version']+1)
        self.assertTrue((self.root/before['path']).exists())
    def test_probe_requires_actual_values_not_echoed_versions(self):
        packs=build_common_packs(self.root)
        valid={'status':'ready','work_id':'example','sources':[{'filename':p['filename'],'source_probe':p['source_probe']} for p in packs]}
        self.assertEqual(verify_source_probe(valid,'example',packs)['work_id'],'example')
        valid['sources'][0]['source_probe']='invented'
        with self.assertRaises(AutomationError):verify_source_probe(valid,'example',packs)
    def test_tampered_pack_rejected(self):
        pack=build_common_packs(self.root)[0];(self.root/pack['path']).write_text('tampered')
        with self.assertRaises(AutomationError):build_common_packs(self.root)
