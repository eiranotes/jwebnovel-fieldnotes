import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import preference_feedback
from preference_atoms import ATOMIZER_VERSION, extract_note_atoms
from preference_rank import rank_candidates, score_candidate


class PreferenceAtomTests(unittest.TestCase):
    def test_current_user_notes_extract_specific_atoms(self):
        atoms = extract_note_atoms("빠르고 궁금한 전개. 경파한 캐릭터 성격")
        keys = {(x["key"], x["polarity"]) for x in atoms}
        self.assertIn(("pacing:fast", 1), keys)
        self.assertIn(("hook:curiosity", 1), keys)
        self.assertIn(("characters:breezy_energy", 1), keys)

        atoms = extract_note_atoms("그럴듯하게 묘사만 할뿐이고 주인공도 설득력이떨어짐. 게임 자체도 재미가 없음")
        keys = {(x["key"], x["polarity"]) for x in atoms}
        self.assertIn(("prose:surface_only", -1), keys)
        self.assertIn(("protagonist:implausible", -1), keys)
        self.assertIn(("core:unfun", -1), keys)

        atoms = extract_note_atoms("경어 묘사는 별로.")
        keys = {(x["key"], x["polarity"]) for x in atoms}
        self.assertIn(("prose:formal_honorific", -1), keys)
        self.assertNotIn(("prose:polished", -1), keys)

    def test_rebuild_generates_pairwise_preferences_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "workspace").mkdir()
            (root / "config").mkdir()
            (root / "data").mkdir()
            feedback = root / "workspace" / "preference-feedback.json"
            model = root / "workspace" / "preference-model.json"
            profiles = root / "config" / "search-profiles.json"
            daily = root / "workspace" / "daily-taste-state.json"
            work_index = root / "data" / "work-index.json"
            traces = root / "workspace" / "preference-ranking-traces.json"
            history = root / "workspace" / "preference-learning-history.json"
            profiles.write_text(json.dumps({"profiles":[{"profile_id":"p","learned_preferences":{}}]}), encoding="utf-8")
            daily.write_text(json.dumps({"responses":[]}), encoding="utf-8")
            work_index.write_text(json.dumps({"works":[]}), encoding="utf-8")
            traces.write_text(json.dumps({"contexts":{}}), encoding="utf-8")
            feedback.write_text(json.dumps({"events":[
                {"canonical_key":"a","profile_id":"p","verdict":"love","score":3,"rating":5,"context_id":"e1","recommended_rank":"A1","reasons":[],"tags":[],"note":"빠르고 궁금한 전개","atoms":extract_note_atoms("빠르고 궁금한 전개")},
                {"canonical_key":"b","profile_id":"p","verdict":"dislike","score":-1,"rating":2,"context_id":"e1","recommended_rank":"A2","reasons":[],"tags":[],"note":"전체적으로 애매","atoms":extract_note_atoms("전체적으로 애매")},
            ]}), encoding="utf-8")

            previous = (preference_feedback.FEEDBACK, preference_feedback.MODEL, preference_feedback.PROFILES, preference_feedback.DAILY_TASTE, preference_feedback.WORK_INDEX, preference_feedback.RANKING_TRACES, preference_feedback.LEARNING_HISTORY)
            try:
                preference_feedback.FEEDBACK = feedback
                preference_feedback.MODEL = model
                preference_feedback.PROFILES = profiles
                preference_feedback.DAILY_TASTE = daily
                preference_feedback.WORK_INDEX = work_index
                preference_feedback.RANKING_TRACES = traces
                preference_feedback.LEARNING_HISTORY = history
                result = preference_feedback.rebuild()
            finally:
                (preference_feedback.FEEDBACK, preference_feedback.MODEL, preference_feedback.PROFILES, preference_feedback.DAILY_TASTE, preference_feedback.WORK_INDEX, preference_feedback.RANKING_TRACES, preference_feedback.LEARNING_HISTORY) = previous

            learned = result["profiles"]["p"]
            self.assertEqual(learned["pairwise_preferences"][0]["winner"], "a")
            self.assertEqual(learned["pairwise_preferences"][0]["loser"], "b")
            self.assertEqual(learned["metrics"]["pairwise_accuracy"], 1.0)
            self.assertGreater(learned["metrics"]["high_rating_rate"], 0)

    def test_rebuild_reextracts_atoms_when_atomizer_version_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "workspace").mkdir()
            (root / "config").mkdir()
            (root / "data").mkdir()
            feedback = root / "workspace" / "preference-feedback.json"
            model = root / "workspace" / "preference-model.json"
            profiles = root / "config" / "search-profiles.json"
            daily = root / "workspace" / "daily-taste-state.json"
            work_index = root / "data" / "work-index.json"
            traces = root / "workspace" / "preference-ranking-traces.json"
            history = root / "workspace" / "preference-learning-history.json"
            profiles.write_text(json.dumps({"profiles":[]}), encoding="utf-8")
            daily.write_text(json.dumps({"responses":[]}), encoding="utf-8")
            work_index.write_text(json.dumps({"works":[]}), encoding="utf-8")
            traces.write_text(json.dumps({"contexts":{}}), encoding="utf-8")
            feedback.write_text(json.dumps({"events":[{
                "canonical_key":"a","verdict":"neutral","score":0,"rating":3,
                "note":"경어 묘사는 별로.","atoms":[{"key":"prose:polished","polarity":-1}],
                "atomizer_version":"1.0","reasons":[],"tags":[]
            }]}), encoding="utf-8")
            previous = (preference_feedback.FEEDBACK, preference_feedback.MODEL, preference_feedback.PROFILES, preference_feedback.DAILY_TASTE, preference_feedback.WORK_INDEX, preference_feedback.RANKING_TRACES, preference_feedback.LEARNING_HISTORY)
            try:
                preference_feedback.FEEDBACK = feedback
                preference_feedback.MODEL = model
                preference_feedback.PROFILES = profiles
                preference_feedback.DAILY_TASTE = daily
                preference_feedback.WORK_INDEX = work_index
                preference_feedback.RANKING_TRACES = traces
                preference_feedback.LEARNING_HISTORY = history
                preference_feedback.rebuild()
                migrated = json.loads(feedback.read_text(encoding="utf-8"))["events"][0]
            finally:
                (preference_feedback.FEEDBACK, preference_feedback.MODEL, preference_feedback.PROFILES, preference_feedback.DAILY_TASTE, preference_feedback.WORK_INDEX, preference_feedback.RANKING_TRACES, preference_feedback.LEARNING_HISTORY) = previous
            self.assertEqual(migrated["atomizer_version"], ATOMIZER_VERSION)
            keys = {x["key"] for x in migrated["atoms"]}
            self.assertIn("prose:formal_honorific", keys)
            self.assertNotIn("prose:polished", keys)

    def test_one_note_has_bounded_total_atom_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "workspace").mkdir()
            (root / "config").mkdir()
            (root / "data").mkdir()
            feedback = root / "workspace" / "preference-feedback.json"
            model = root / "workspace" / "preference-model.json"
            profiles = root / "config" / "search-profiles.json"
            daily = root / "workspace" / "daily-taste-state.json"
            work_index = root / "data" / "work-index.json"
            traces = root / "workspace" / "preference-ranking-traces.json"
            history = root / "workspace" / "preference-learning-history.json"
            profiles.write_text(json.dumps({"profiles":[]}), encoding="utf-8")
            daily.write_text(json.dumps({"responses":[]}), encoding="utf-8")
            work_index.write_text(json.dumps({"works":[]}), encoding="utf-8")
            traces.write_text(json.dumps({"contexts":{}}), encoding="utf-8")
            note = "빠르고 궁금한 전개. 경파한 캐릭터 성격"
            feedback.write_text(json.dumps({"events":[{
                "canonical_key":"a","verdict":"love","score":3,"rating":5,"note":note,
                "atoms":extract_note_atoms(note),"atomizer_version":ATOMIZER_VERSION,"reasons":[],"tags":[]
            }]}), encoding="utf-8")
            previous = (preference_feedback.FEEDBACK, preference_feedback.MODEL, preference_feedback.PROFILES, preference_feedback.DAILY_TASTE, preference_feedback.WORK_INDEX, preference_feedback.RANKING_TRACES, preference_feedback.LEARNING_HISTORY)
            try:
                preference_feedback.FEEDBACK = feedback
                preference_feedback.MODEL = model
                preference_feedback.PROFILES = profiles
                preference_feedback.DAILY_TASTE = daily
                preference_feedback.WORK_INDEX = work_index
                preference_feedback.RANKING_TRACES = traces
                preference_feedback.LEARNING_HISTORY = history
                learned = preference_feedback.rebuild()["profiles"]["__global__"]
            finally:
                (preference_feedback.FEEDBACK, preference_feedback.MODEL, preference_feedback.PROFILES, preference_feedback.DAILY_TASTE, preference_feedback.WORK_INDEX, preference_feedback.RANKING_TRACES, preference_feedback.LEARNING_HISTORY) = previous
            atoms = learned["atom_signals"]
            self.assertLessEqual(sum(x["support"] for x in atoms), 1.001)
            self.assertTrue(all(x["stage"] == "tentative" for x in atoms))
            self.assertTrue(all(abs(x["effective_weight"]) < .21 for x in atoms))


if __name__ == "__main__":
    unittest.main()
