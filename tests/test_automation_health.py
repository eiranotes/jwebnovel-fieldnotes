import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("automation_health", HERE / "scripts/automation_health.py")
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)

NOW = datetime(2026, 10, 9, 10, 0, 0, tzinfo=timezone.utc)


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rel = "workspace/2026-10-09/test/test-novel"
        write(self.root / "config/automation.json", {"enabled": True})
        write(self.root / "data/automation-status.json",
              {"updated_at": "2026-10-01T00:00:00Z"})
        write(self.root / "data/work-registry.json", {
            "works": [{"work_id": "test-novel", "workspace": self.rel,
                       "status": "translation_pending",
                       "prepared_at": "2026-10-07T00:00:00Z"}],
        })
        self.manifest = self.root / self.rel / "translation/manifest.json"
        write(self.manifest, {"chunks": [
            {"chunk_id": "0001", "status": "done"},
            {"chunk_id": "0002", "status": "pending"},
            {"chunk_id": "0003", "status": "pending"},
        ]})

    def snapshot(self, **extra):
        p = self.root / "worker.json"
        write(p, {"workspace": "shared-automation",
                  "observed_at": "2026-10-09T09:59:00Z",
                  "capabilities": ["fieldnotes.karu.project.translate"],
                  "status": "ready", **extra})
        return p

    def test_missing_heartbeat_is_unknown_not_success(self):
        before = self.manifest.read_bytes()
        result = health.audit(self.root, now=NOW)
        self.assertEqual(result["model_worker"]["status"], "unknown")
        self.assertEqual(result["work_state_counts"]["awaiting_worker_observation"], 1)
        self.assertEqual(result["pending_chunks"], 2)
        self.assertFalse(result["auto_translation_submitted"])
        self.assertFalse(result["safe_to_resubmit_uncertain_translation"])
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_queue_inspector_cannot_pose_as_translation_worker(self):
        status = self.snapshot(capabilities=["fieldnotes.queue.inspect"])
        result = health.audit(self.root, now=NOW, worker_snapshot_path=status)
        self.assertEqual(result["model_worker"]["status"], "unavailable")
        self.assertEqual(result["work_state_counts"]["worker_unavailable"], 1)
        self.assertEqual(result["works_needing_attention"][0]["pending_chunks"], 2)

    def test_fresh_translator_with_stale_chunks_flags_stalled(self):
        status = self.snapshot()
        result = health.audit(self.root, now=NOW, worker_snapshot_path=status)
        self.assertEqual(result["model_worker"]["status"], "ready")
        self.assertEqual(result["work_state_counts"]["stalled"], 1)
        self.assertIsNotNone(result["status_projection_age_hours"])

    def test_recent_progress_is_queued(self):
        state = self.root / self.rel / "state.json"
        write(state, {"status": "translation_pending",
                      "updated_at": "2026-10-09T09:55:00Z"})
        result = health.audit(self.root, now=NOW, worker_snapshot_path=self.snapshot())
        self.assertEqual(result["work_state_counts"]["queued"], 1)
        self.assertEqual(result["works_needing_attention"], [])

    def test_expired_heartbeat_is_not_translator_ready(self):
        result = health.audit(self.root, now=NOW,
                              worker_snapshot_path=self.snapshot(
                                  observed_at="2026-10-08T00:00:00Z"))
        self.assertEqual(result["model_worker"]["reason"], "MODEL_WORKER_HEARTBEAT_STALE")

    def test_registry_path_escape_is_rejected_without_file_access(self):
        write(self.root / "data/work-registry.json",
              {"works": [{"work_id": "test-novel",
                          "workspace": "workspace/../../private", "status": "translation_pending"}]})
        result = health.audit(self.root, now=NOW)
        self.assertEqual(result["work_state_counts"]["invalid_workspace_path"], 1)


if __name__ == "__main__":
    unittest.main()
