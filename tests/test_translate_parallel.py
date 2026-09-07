import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from translate_parallel import preexisting_quarantine


class TranslateParallelTests(unittest.TestCase):
    def test_preexisting_uncertain_operation_is_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            d=root/"workspace/automation-runs/backend/demo/translator"
            d.mkdir(parents=True)
            (d/"op.json").write_text(json.dumps({
                "state":"uncertain",
                "operation_id":"op-123",
                "last_error":"CHATGPT_BOOTSTRAP_SUBMISSION_UNCERTAIN_AFTER_SEND"
            }), encoding="utf-8")
            self.assertEqual(preexisting_quarantine("demo", root), {
                "work_id":"demo",
                "operation_id":"op-123",
                "error":"CHATGPT_BOOTSTRAP_SUBMISSION_UNCERTAIN_AFTER_SEND"
            })

    def test_failed_or_complete_operation_is_not_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            d=root/"workspace/automation-runs/backend/demo/translator"
            d.mkdir(parents=True)
            (d/"failed.json").write_text(json.dumps({"state":"failed"}), encoding="utf-8")
            (d/"complete.json").write_text(json.dumps({"state":"complete"}), encoding="utf-8")
            self.assertIsNone(preexisting_quarantine("demo", root))


if __name__ == "__main__": unittest.main()
