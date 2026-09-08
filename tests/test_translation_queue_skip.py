import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import translation_queue


class TranslationQueueSkipTests(unittest.TestCase):
    def test_skipped_work_is_not_selected_as_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            registry=root/'data/work-registry.json'
            registry.parent.mkdir(parents=True)
            work=root/'workspace/2026-09-08/entry/known'
            (work/'translation').mkdir(parents=True)
            registry.write_text(json.dumps({'works':[{'work_id':'known','workspace':'workspace/2026-09-08/entry/known'}]}))
            (work/'translation/manifest.json').write_text(json.dumps({'chunks':[{'chunk_id':'0001','status':'pending'}]}))
            (work/'state.json').write_text(json.dumps({'status':'translation_skipped','updated_at':'now'}))
            old_root,old_registry=translation_queue.ROOT,translation_queue.REGISTRY
            try:
                translation_queue.ROOT=root;translation_queue.REGISTRY=registry
                self.assertEqual(translation_queue.pending_works(),[])
            finally:
                translation_queue.ROOT=old_root;translation_queue.REGISTRY=old_registry


if __name__=='__main__':unittest.main()
