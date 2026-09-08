import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from automation_store import atomic_json,read_json
from refresh_automation_status import refresh,sync_registry_progress


class RefreshAutomationStatusTests(unittest.TestCase):
    def test_workspace_translation_state_projects_back_to_registry_and_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            for folder in ('config','data','workspace/2026-09-07/entry/example/translation'):
                (root/folder).mkdir(parents=True,exist_ok=True)
            atomic_json(root/'config/automation.json',{'enabled':False,'time':None})
            atomic_json(root/'config/search-profiles.json',{'criteria_ready':False,'profiles':[]})
            atomic_json(root/'config/project-translation.json',{'backend':'webgpt_project','activation':'verified_live','project_alias':'fieldnotes','require_source_probe':True,
                'fallback':{'enabled':True,'backend':'codex_webgpt'}})
            atomic_json(root/'data/automation-status.json',{'schedule':{},'criteria':{},'translation':{},'source_acquisition':{}})
            atomic_json(root/'data/work-registry.json',{'works':[{'work_id':'example','workspace':'workspace/2026-09-07/entry/example','status':'translation_pending'}]})
            atomic_json(root/'workspace/2026-09-07/entry/example/state.json',{'status':'translation_complete','chunks_done':2,'chunks_total':2,'updated_at':'now'})
            atomic_json(root/'workspace/2026-09-07/entry/example/translation/manifest.json',{'chunk_count':2,'chunks':[]})

            self.assertTrue(sync_registry_progress(root))
            row=read_json(root/'data/work-registry.json')['works'][0]
            self.assertEqual((row['status'],row['chunks_done'],row['chunks_total']),('translation_complete',2,2))
            self.assertFalse(sync_registry_progress(root))
            status=refresh(root)
            self.assertEqual(status['translation']['completed_chunks'],2)
            self.assertEqual(status['translation']['pending_chunks'],0)
            self.assertEqual(status['translation']['backend']['activation'],'verified_live')
            self.assertTrue(status['translation']['backend']['allow_fallback'])
            self.assertEqual(status['translation']['backend']['fallback_backend'],'codex_webgpt')

    def test_skipped_translation_projects_to_registry_without_pending_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            for folder in ('config','data','workspace/2026-09-07/entry/skipped/translation'):
                (root/folder).mkdir(parents=True,exist_ok=True)
            atomic_json(root/'config/automation.json',{'enabled':False,'time':None})
            atomic_json(root/'config/search-profiles.json',{'criteria_ready':False,'profiles':[]})
            atomic_json(root/'config/project-translation.json',{'backend':'webgpt_project','activation':'verified_live','project_alias':'fieldnotes','require_source_probe':True,'fallback':{'enabled':False,'backend':'codex_webgpt'}})
            atomic_json(root/'data/automation-status.json',{'schedule':{},'criteria':{},'translation':{},'source_acquisition':{}})
            atomic_json(root/'data/work-registry.json',{'works':[{'work_id':'skipped','workspace':'workspace/2026-09-07/entry/skipped','status':'translation_pending'}]})
            atomic_json(root/'workspace/2026-09-07/entry/skipped/state.json',{'status':'translation_skipped','chunks_done':0,'chunks_total':5,'updated_at':'now'})
            atomic_json(root/'workspace/2026-09-07/entry/skipped/translation/manifest.json',{'chunk_count':5,'chunks':[{'status':'pending'}]*5})

            status=refresh(root)
            row=read_json(root/'data/work-registry.json')['works'][0]
            self.assertEqual(row['status'],'translation_skipped')
            self.assertEqual(status['translation']['pending_chunks'],0)
            self.assertEqual(status['translation']['completed_chunks'],0)

    def test_registry_projection_refuses_workspace_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'data').mkdir();(root/'workspace').mkdir()
            atomic_json(root/'data/work-registry.json',{'works':[{'work_id':'bad','workspace':'../outside','status':'translation_pending'}]})
            self.assertFalse(sync_registry_progress(root))
            self.assertEqual(read_json(root/'data/work-registry.json')['works'][0]['status'],'translation_pending')


if __name__=='__main__':unittest.main()
