import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from automation_store import AutomationError, atomic_json
from project_context import build_common, build_work, public_pack, source_probe_task, verify_source_probe


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        source=Path(__file__).resolve().parents[1]/'templates/project-context'
        destination=self.root/'templates/project-context';destination.mkdir(parents=True)
        for f in source.glob('*.md'):(destination/f.name).write_text(f.read_text())
        self.work=self.root/'workspace/books/example';self.work.mkdir(parents=True)
        atomic_json(self.work/'metadata.json',{'work_id':'example','title':'Example','author':'Test'})
        atomic_json(self.work/'glossary.json',{'ruby_notes':{'紅':'くれない'},'people':{}})
    def tearDown(self): self.tmp.cleanup()
    def test_stable_revision_and_no_probe_in_prompt(self):
        work=build_work(self.work,self.root);common=build_common(self.root)
        self.assertEqual(work,build_work(self.work,self.root))
        prompt=source_probe_task('example',common,work)
        self.assertNotIn(work['source_probe'],json.dumps(prompt))
        self.assertNotIn(common['source_probe'],json.dumps(prompt))
        self.assertIn('くれない',(self.root/work['path']).read_text())
        self.assertNotIn('source_probe',public_pack(work))
    def test_revision_changes_with_glossary_and_old_file_survives(self):
        before=build_work(self.work,self.root)
        atomic_json(self.work/'glossary.json',{'people':{'紅':'쿠레나이'}})
        after=build_work(self.work,self.root)
        self.assertEqual(after['context_version'],before['context_version']+1)
        self.assertTrue((self.root/before['path']).exists())
    def test_probe_requires_actual_values_not_echoed_versions(self):
        packs=[build_common(self.root),build_work(self.work,self.root)]
        valid={'status':'ready','work_id':'example','sources':[{'filename':p['filename'],'source_probe':p['source_probe']} for p in packs]}
        self.assertEqual(verify_source_probe(valid,'example',packs)['work_id'],'example')
        valid['sources'][0]['source_probe']='invented'
        with self.assertRaises(AutomationError):verify_source_probe(valid,'example',packs)
    def test_tampered_pack_rejected(self):
        pack=build_work(self.work,self.root);(self.root/pack['path']).write_text('tampered')
        with self.assertRaises(AutomationError):build_work(self.work,self.root)
    def test_path_escape_rejected(self):
        with self.assertRaises(AutomationError):build_work(self.root/'templates',self.root)
