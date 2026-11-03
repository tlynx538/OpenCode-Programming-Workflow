"""Regression checks for utilities extracted from the removed controller."""
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.opencode/runtime'))
import runtime


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        runtime.execute(['git', 'init', '-q', str(self.root)])
        (self.root / 'app.py').write_text('print("hello")\n')
        (self.root / '.gitignore').write_text('.env\nnode_modules/\n')
        runtime.git(self.root, 'add', '.')

    def tearDown(self):
        self.directory.cleanup()

    def test_capture_bounds_required_results_and_drains_both_streams(self):
        with self.assertRaisesRegex(runtime.SandboxError, 'capture budget'):
            runtime.capture([sys.executable, '-c',
                             'import sys; sys.stdout.write("x"*100000); sys.stderr.write("y"*100000)'], limit=1024)
        result = runtime.capture([sys.executable, '-c', 'print("small required result")'])
        self.assertEqual(result.stdout, b'small required result\n')

    def test_capture_timeout_reaps_owned_child(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            runtime.capture([sys.executable, '-c', 'import time; time.sleep(60)'], timeout=.05)

    def test_build_snapshot_excludes_secrets_configuration_and_ignored_dependencies(self):
        (self.root / '.env').write_text('not for the sandbox')
        (self.root / 'secret.key').write_text('not for the sandbox')
        (self.root / '.opencode').mkdir()
        (self.root / '.opencode/opencode.json').write_text('{}')
        (self.root / 'node_modules').mkdir()
        (self.root / 'node_modules/dependency.js').write_text('host dependency')
        runtime.git(self.root, 'add', 'secret.key', '.opencode/opencode.json')
        with runtime.mirror(self.root) as snapshot:
            self.assertTrue((snapshot / 'app.py').exists())
            for name in ('.env', 'secret.key', '.opencode', 'node_modules', '.git'):
                self.assertFalse((snapshot / name).exists(), name)
        self.assertEqual((self.root / '.env').read_text(), 'not for the sandbox')

    def test_snapshot_rejects_symlinks_instead_of_following_them(self):
        (self.root / 'link.py').symlink_to(self.root / 'app.py')
        with self.assertRaisesRegex(runtime.SandboxError, 'Symlink'):
            with runtime.mirror(self.root):
                self.fail('A symlink was copied')

    def test_source_manifest_detects_content_and_executable_bit_changes(self):
        original = runtime.source_files(self.root)
        (self.root / 'app.py').write_text('print("changed")\n')
        changed = runtime.source_files(self.root)
        self.assertNotEqual(original, changed)
        (self.root / 'app.py').chmod(0o755)
        self.assertNotEqual(changed, runtime.source_files(self.root))

    def test_command_evidence_is_bounded_and_both_streams_are_drained(self):
        with redirect_stderr(io.StringIO()):
            result = runtime.run_logged([sys.executable, '-c', 'import sys; print("x"*200000); print("y"*200000,file=sys.stderr)'], timeout=10, limit=4096)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout), 4096)
        self.assertEqual(len(result.stderr), 4096)


class NonGitRuntimeTests(unittest.TestCase):
    def test_snapshot_filters_nested_repositories_dependencies_secrets_and_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('oslo/app.py', 'osaka/task.py', 'oslo/.git/config', 'oslo/.env',
                         'osaka/node_modules/dep.js', '.opencode/workspace/settings.json', '.aws/config'):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('source')
            before = runtime.fingerprint(root)
            self.assertEqual(set(runtime.source_files(root)), {'oslo/app.py', 'osaka/task.py'})
            with runtime.mirror(root) as snapshot:
                self.assertEqual({p.relative_to(snapshot).as_posix() for p in snapshot.rglob('*') if p.is_file()},
                                 {'oslo/app.py', 'osaka/task.py'})
            (root / '.opencode/workspace/settings.json').write_text('state update')
            self.assertEqual(runtime.fingerprint(root), before)
            (root / 'oslo/app.py').chmod(0o755)
            self.assertNotEqual(runtime.fingerprint(root), before)
            (root / 'escape').symlink_to(root.parent)
            with self.assertRaisesRegex(runtime.SandboxError, 'Symlink'):
                runtime.source_files(root)

    def test_missing_git_binary_and_empty_git_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'app.py').write_text('source')
            with patch.object(runtime, 'capture', side_effect=FileNotFoundError('git')):
                self.assertEqual(set(runtime.source_files(root)), {'app.py'})
                self.assertTrue(runtime.fingerprint(root))
            runtime.execute(['git', 'init', '-q', str(root)])
            runtime.git(root, 'add', 'app.py')
            self.assertTrue(runtime.fingerprint(root))

    def test_git_worktree_state_stays_in_the_shared_git_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'main'
            root.mkdir()
            runtime.execute(['git', 'init', '-q', str(root)])
            runtime.git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        'commit', '--allow-empty', '-qm', 'fixture')
            worktree = Path(directory) / 'worktree'
            runtime.git(root, 'worktree', 'add', '-qb', 'other', str(worktree))
            self.assertTrue((worktree / '.git').is_file())
            self.assertEqual(runtime.workspace_home(root), runtime.workspace_home(worktree))
            self.assertEqual(runtime.workspace_home(worktree), root / '.git/bdfl')

    def test_non_git_state_rejects_external_symlinks_and_missing_workspaces(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            (root / '.opencode').symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(runtime.SandboxError, 'symlink'):
                runtime.workspace_home(root)
            with self.assertRaisesRegex(runtime.SandboxError, 'does not exist'):
                runtime.repository_root(root / 'missing')


if __name__ == '__main__':
    unittest.main()
