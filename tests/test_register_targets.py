import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))


def load_module():
    path=Path(__file__).resolve().parents[1]/"scripts"/"register_targets.py"
    spec=importlib.util.spec_from_file_location("register_targets_tested",path)
    module=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
    return module


class RegisterTargetsTests(unittest.TestCase):
    def test_canonical_key_accepts_explicit_null_author(self):
        mod=load_module()
        self.assertEqual(mod.canonical_key({"title":"  Test ","author":None}),"test|")
        self.assertEqual(mod.canonical_key({"title":None,"author":None}),"|")

if __name__=="__main__": unittest.main()
