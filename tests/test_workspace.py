"""Native workspace tools do not authorize or orchestrate agents."""
import json
import contextlib
import io
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_sandbox as fixtures
import workspace
import sandbox
import runtime


class WorkspaceTests(unittest.TestCase):
    setUp = fixtures.SandboxTests.setUp
    tearDown = fixtures.SandboxTests.tearDown

    def call(self, action, **values):
        return workspace.dispatch(self.root, {'action': action, 'session_id': 'opencode-session', **values})

    def test_configuration_requires_only_test_and_sandbox_settings(self):
        self.call('configure', tests=self.policy['tests'], sandbox={})
        saved = sandbox.load(self.root)
        self.assertEqual(saved['version'], 2)
        self.assertEqual(set(saved['policy']), {'tests'})
        self.assertNotIn('authorization', saved)
        self.assertEqual(runtime.git(self.root, 'status', '--porcelain'), b'')

    def test_actual_evidence_is_saved_without_a_controller_run(self):
        with patch.object(runtime, 'run_logged', return_value=subprocess.CompletedProcess([], 0, b'PASS', b'')):
            result = self.call('test', operation_id='a' * 32)
        self.assertTrue(result['passed'])
        self.assertTrue((sandbox.home(self.root) / 'evidence' / ('a' * 32 + '.json')).exists())
        self.assertFalse((sandbox.home(self.root) / 'runs').exists())
        self.assertEqual(self.call('status')['latest_test']['candidate'], result['candidate'])

    def test_source_changes_make_evidence_stale(self):
        def run(argv, timeout):
            (self.root / 'app.py').write_text('changed during tests\n')
            return subprocess.CompletedProcess(argv, 0, b'PASS', b'')
        with patch.object(runtime, 'run_logged', side_effect=run):
            result = self.call('test')
        self.assertTrue(result['stale'])
        self.assertFalse(result['passed'])

    def test_controller_submission_is_not_a_workspace_capability(self):
        for action in ('submit', 'authorize', 'resume'):
            with self.subTest(action=action), self.assertRaisesRegex(runtime.SandboxError, 'Unknown workspace action'):
                self.call(action)
        self.assertFalse((sandbox.home(self.root) / 'runs').exists())


class NonGitWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = workspace.Path(self.tmp.name)
        (self.root / 'app.py').write_text('print("hello")\n')
        self.policy = json.loads((runtime.BUNDLE / 'runtime/settings.example.json').read_text())['policy']
        self.session = sandbox.SessionSandbox(self.root, 'opencode-session')
        self.docker = fixtures.Docker(self.session)
        for method, fake in (('execute', self.docker.execute), ('capture', self.docker.run)):
            patcher = patch.object(runtime, method, side_effect=fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def cli(self, action, mode='call', identifier=None, **values):
        output = io.StringIO()
        argv = ['--repo', str(self.root), mode] + ([identifier] if identifier else [])
        payload = {'action': action, 'session_id': 'opencode-session', **values}
        with patch.object(workspace.sys, 'stdin', io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(output):
            code = workspace.main(argv)
        return code, output.getvalue()

    def test_non_git_cli_lifecycle_records_real_test_evidence_and_logs(self):
        code, output = self.cli('session_start')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)['status'], 'needs_configuration')
        code, output = self.cli('configure', tests=self.policy['tests'], sandbox={})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)['sandbox']['status'], 'active')
        with patch.object(runtime, 'run_logged', return_value=subprocess.CompletedProcess([], 0, b'PASS', b'')):
            code, output = self.cli('test', operation_id='c' * 32)
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertTrue(result['passed'])
        self.assertTrue(workspace.Path(result['evidence_file']).is_file())
        code, output = self.cli('status')
        self.assertEqual(json.loads(output)['latest_test']['candidate'], result['candidate'])
        import logs
        log = io.BytesIO()
        logs.follow(self.root, 'c' * 32, output=log)
        self.assertIn(b'operation completed', log.getvalue())
        code, output = self.cli('end_sandbox')
        self.assertEqual(code, 0)
        self.assertFalse(self.docker.exists)
        self.assertTrue(sandbox.settings_path(self.root).is_file())
        self.assertFalse((self.root / '.git').exists())

    def test_unconfigured_tests_fail_honestly_and_state_is_outside_snapshot(self):
        before = runtime.fingerprint(self.root)
        code, output = self.cli('test')
        self.assertEqual(code, 1)
        self.assertIn('Configure project', json.loads(output)['error'])
        self.assertEqual(runtime.fingerprint(self.root), before)
        code, output = self.cli(None, mode='state-home')
        self.assertEqual(json.loads(output)['directory'], str(self.root / '.opencode/workspace'))

    def test_non_git_test_failure_and_source_changes_are_not_reported_as_success(self):
        self.cli('configure', tests=self.policy['tests'], sandbox={})
        def changed(argv, timeout):
            (self.root / 'app.py').write_text('changed during testing')
            return subprocess.CompletedProcess(argv, 0, b'PASS', b'')
        with patch.object(runtime, 'run_logged', side_effect=changed):
            code, output = self.cli('test')
        result = json.loads(output)
        self.assertEqual(code, 0)
        self.assertTrue(result['stale'])
        self.assertFalse(result['passed'])
        with patch.object(runtime, 'run_logged', return_value=subprocess.CompletedProcess([], 1, b'', b'FAIL')):
            code, output = self.cli('test')
        self.assertFalse(json.loads(output)['passed'])


if __name__ == '__main__':
    unittest.main()
