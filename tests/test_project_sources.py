import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from automation_store import digest
from project_sources import PROJECT_INSTRUCTIONS_STATE, synchronize


class FakeProjectBridge:
    def __init__(self):
        self.inspect_body = None
        self.target = {
            'alias': 'fieldnotes',
            'name': 'Fieldnotes',
            'url': 'https://chatgpt.com/g/g-p-test-fieldnotes/project',
        }

    def request(self, route, body=None, method='GET'):
        if route == '/automation-projects/registry':
            return {'entries': {'fieldnotes': self.target}}
        if route == '/automation-projects/inspect':
            self.inspect_body = json.loads(json.dumps(body))
            return {'commandId': 'abcdef1234567890'}
        if route == '/automation-projects/result?id=abcdef1234567890':
            return {
                'state': 'complete',
                'result': {
                    'sourceSync': {
                        'state': 'listed',
                        'filenames': [row['filename'] for row in self.inspect_body['sourceFiles']],
                        'instructionsSaved': True,
                    }
                },
            }
        raise AssertionError(route)


class ProjectSourceInstructionCASTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'templates/project-context').mkdir(parents=True)
        pack_path = self.root / 'workspace/project-context/GLOBAL_CONTEXT/GLOBAL_CONTEXT_v0001_fixture.md'
        pack_path.parent.mkdir(parents=True)
        pack_path.write_text('# fixture\n', encoding='utf-8')
        self.pack = {
            'source_name': 'GLOBAL_CONTEXT',
            'filename': pack_path.name,
            'context_version': 1,
            'content_hash': 'a' * 64,
            'file_sha256': digest(pack_path.read_bytes()),
            'path': str(pack_path.relative_to(self.root)),
        }
        self.bridge = FakeProjectBridge()

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_managed_instruction_migration_uses_exact_tracked_baseline(self):
        old = 'historically verified provider instructions\n'
        desired = 'new managed provider instructions\n'
        (self.root / 'templates/project-context/PROJECT_INSTRUCTIONS_BASELINE.md').write_text(old, encoding='utf-8')
        (self.root / 'templates/project-context/PROJECT_INSTRUCTIONS.md').write_text(desired, encoding='utf-8')

        result = synchronize([self.pack], root=self.root, bridge=self.bridge, instructions=True, timeout=1, poll_interval=0)

        self.assertEqual(result['state'], 'complete')
        self.assertEqual(self.bridge.inspect_body['projectInstructions'], desired)
        self.assertEqual(self.bridge.inspect_body['expectedProjectInstructions'], old)
        state = json.loads((self.root / PROJECT_INSTRUCTIONS_STATE).read_text())
        self.assertTrue(state['verified'])
        self.assertEqual(state['text'], desired)
        self.assertEqual(state['sha256'], digest(desired.encode('utf-8')))

    def test_last_provider_verified_value_supersedes_bootstrap_baseline(self):
        baseline = 'old bootstrap baseline\n'
        verified = 'last verified live value\n'
        desired = 'next managed value\n'
        (self.root / 'templates/project-context/PROJECT_INSTRUCTIONS_BASELINE.md').write_text(baseline, encoding='utf-8')
        (self.root / 'templates/project-context/PROJECT_INSTRUCTIONS.md').write_text(desired, encoding='utf-8')
        state_path = self.root / PROJECT_INSTRUCTIONS_STATE
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({'version': 1, 'verified': True, 'text': verified}) + '\n', encoding='utf-8')

        synchronize([self.pack], root=self.root, bridge=self.bridge, instructions=True, timeout=1, poll_interval=0)

        self.assertEqual(self.bridge.inspect_body['expectedProjectInstructions'], verified)
        self.assertNotEqual(self.bridge.inspect_body['expectedProjectInstructions'], baseline)
        state = json.loads(state_path.read_text())
        self.assertEqual(state['text'], desired)


if __name__ == '__main__':
    unittest.main()
