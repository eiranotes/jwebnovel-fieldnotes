import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from learning_store import active_context, load_store, observe, seed_known


class LearningStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir(parents=True)
        policy = json.loads((Path(__file__).resolve().parents[1] / "config" / "learning-policy.json").read_text(encoding="utf-8"))
        (self.root / "config" / "learning-policy.json").write_text(json.dumps(policy), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_is_idempotent_and_active(self):
        first = seed_known(self.root)
        second = seed_known(self.root)
        self.assertGreater(first["added"], 0)
        self.assertEqual(second["added"], 0)
        data = load_store(self.root)
        self.assertEqual(len(data["lessons"]), len({x["lesson_id"] for x in data["lessons"]}))
        ctx = active_context("translation", root=self.root)
        self.assertTrue(any(x["lesson_id"] == "translation.invalid-json-repair" for x in ctx["lessons"]))

    def test_new_error_is_not_active_until_verified_resolution(self):
        lesson = observe("discovery", "new false positive", "observed", scope="ranking", root=self.root)
        self.assertEqual(lesson["status"], "observed")
        self.assertFalse(any(x["signature"] == "new false positive" for x in active_context("discovery", root=self.root)["lessons"]))
        lesson = observe(
            "discovery",
            "new false positive",
            "resolved",
            scope="ranking",
            resolution="Verified fix",
            guard="Only this signature",
            root=self.root,
        )
        self.assertEqual(lesson["status"], "active")
        self.assertTrue(any(x["signature"] == "new false positive" for x in active_context("discovery", root=self.root)["lessons"]))

    def test_regressions_can_demote_a_lesson(self):
        observe("translation", "fragile", "resolved", resolution="fix", root=self.root)
        observe("translation", "fragile", "regression", root=self.root)
        lesson = observe("translation", "fragile", "regression", root=self.root)
        self.assertEqual(lesson["status"], "observed")


if __name__ == "__main__":
    unittest.main()
