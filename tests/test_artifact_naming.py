import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from artifact_naming import alternating_translation_filename, safe_title_filename


class ArtifactNamingTests(unittest.TestCase):
    def test_alternating_translation_uses_original_title(self):
        self.assertEqual(alternating_translation_filename('逆さの茶笠'), '逆さの茶笠 - 번역본.txt')

    def test_filename_sanitizes_only_filesystem_unsafe_characters(self):
        self.assertEqual(alternating_translation_filename('A/B: C?'), 'A_B_ C - 번역본.txt')
        self.assertLessEqual(len(safe_title_filename('가' * 200).encode('utf-8')), 180)
