import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "runtime_sync.py"
    spec = importlib.util.spec_from_file_location("runtime_sync_tested", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class RuntimeSyncTests(unittest.TestCase):
    def test_push_imports_newer_runtime_mutable_state_before_refresh(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            runtime = base / "runtime"
            (root / "config").mkdir(parents=True)
            (runtime / "config").mkdir(parents=True)
            canonical = root / "config" / "search-profiles.json"
            phone = runtime / "config" / "search-profiles.json"
            canonical.write_text(json.dumps({"profiles": [{"name": "old"}]}), encoding="utf-8")
            time.sleep(0.01)
            phone.write_text(json.dumps({"profiles": [{"name": "phone-new"}]}), encoding="utf-8")
            mod.ROOT = root
            mod.RUNTIME = runtime
            mod.RUNTIME_DIRS = ("config",)
            mod.RUNTIME_FILES = ()
            mod.MUTABLE_FILES = ("config/search-profiles.json",)
            mod.PRIVATE_STATE_FILES = ()
            mod.MUTABLE_WORKSPACE_DIRS = ()
            result = mod.push()
            self.assertEqual(result["preserved_runtime"]["files"], 1)
            self.assertEqual(json.loads(canonical.read_text())["profiles"][0]["name"], "phone-new")
            self.assertEqual(json.loads(phone.read_text())["profiles"][0]["name"], "phone-new")

    def test_after_baseline_canonical_only_change_wins_on_push(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); root = base/'repo'; runtime = base/'runtime'
            (root/'config').mkdir(parents=True); (runtime/'config').mkdir(parents=True)
            canonical=root/'config'/'search-profiles.json'; phone=runtime/'config'/'search-profiles.json'
            canonical.write_text('{"value":"base"}',encoding='utf-8'); phone.write_text('{"value":"base"}',encoding='utf-8')
            mod.ROOT=root; mod.RUNTIME=runtime; mod.RUNTIME_DIRS=('config',); mod.RUNTIME_FILES=()
            mod.MUTABLE_FILES=('config/search-profiles.json',); mod.PRIVATE_STATE_FILES=(); mod.MUTABLE_WORKSPACE_DIRS=()
            self.assertEqual(mod.push()['status'],'pushed')
            canonical.write_text('{"value":"canonical-new"}',encoding='utf-8')
            result=mod.push()
            self.assertEqual(result['status'],'pushed')
            self.assertEqual(json.loads(phone.read_text())['value'],'canonical-new')

    def test_after_baseline_two_sided_change_is_conflict(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); root = base/'repo'; runtime = base/'runtime'
            (root/'config').mkdir(parents=True); (runtime/'config').mkdir(parents=True)
            canonical=root/'config'/'search-profiles.json'; phone=runtime/'config'/'search-profiles.json'
            canonical.write_text('{"value":"base"}',encoding='utf-8'); phone.write_text('{"value":"base"}',encoding='utf-8')
            mod.ROOT=root; mod.RUNTIME=runtime; mod.RUNTIME_DIRS=('config',); mod.RUNTIME_FILES=()
            mod.MUTABLE_FILES=('config/search-profiles.json',); mod.PRIVATE_STATE_FILES=(); mod.MUTABLE_WORKSPACE_DIRS=()
            self.assertEqual(mod.push()['status'],'pushed')
            canonical.write_text('{"value":"canonical-new"}',encoding='utf-8')
            phone.write_text('{"value":"phone-new"}',encoding='utf-8')
            result=mod.push()
            self.assertEqual(result['status'],'conflict')
            self.assertEqual(json.loads(canonical.read_text())['value'],'canonical-new')
            self.assertEqual(json.loads(phone.read_text())['value'],'phone-new')


if __name__ == "__main__":
    unittest.main()
