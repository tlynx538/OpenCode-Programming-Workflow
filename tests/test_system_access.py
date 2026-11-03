"""Infrastructure capability boundaries; real namespace/network checks are opt-in."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.opencode/runtime'))
import runtime
spec = importlib.util.spec_from_file_location('system_access', runtime.BUNDLE / 'runtime/system-access.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

CONFIG = {'version': 1, 'servers': {'server': {'ssh': 'fixture'}},
          'postgres': {'db': {'server': 'server', 'database': 'fixture'},
                       'env': {'server': 'server', 'env_file': '/srv/application.env', 'url_key': 'DATABASE_URL'}},
          'mysql': {'db': {'server': 'server', 'database': 'fixture'}},
          'rabbitmq': {'queue': {'server': 'server', 'vhost': 'fixture'}},
          'jenkins': {'ci': {'server': 'server', 'home': '/var/lib/jenkins'}}}


class SystemAccessTests(unittest.TestCase):
    def test_sql_is_generated_from_identifiers_and_cannot_run_raw_mutations(self):
        for kind in ('postgres', 'mysql'):
            for operation in ('tables', 'columns', 'rows'):
                sql = a.sql_query(kind, operation, {'schema': 'public', 'table': 'items', 'query': 'DROP TABLE items'})
                self.assertIn('READ ONLY', sql)
                self.assertIn('ROLLBACK', sql)
                self.assertNotIn('DROP', sql)
            for operation in ('query', 'execute', 'drop'):
                with self.assertRaises(runtime.SandboxError):
                    a.sql_query(kind, operation, {})
        filtered=a.sql_query('postgres','rows',{'table':'items','columns':['id'],'filters':{'id':["x';COMMIT;DELETE FROM items;--",'other']}})
        self.assertIn(' IN (',filtered)
        self.assertNotIn('DELETE',filtered)
        self.assertIn('READ ONLY',filtered)
        for table in ('items;DELETE FROM items', 'x";COMMIT;', '\\! touch /tmp/escape', '../secret'):
            with self.assertRaises(runtime.SandboxError):
                a.sql_query('postgres', 'rows', {'table': table})

    def test_remote_mutations_and_command_injection_never_produce_ssh_commands(self):
        for action, profile in [('server.exec', 'server'), ('rabbitmq.publish', 'queue'),
                                ('rabbitmq.get', 'queue'), ('rabbitmq.purge', 'queue'),
                                ('jenkins.build_now', 'ci'), ('jenkins.script', 'ci'), ('postgres.execute', 'db')]:
            with self.subTest(action=action), self.assertRaises(runtime.SandboxError):
                a.remote_request(CONFIG, action, {'profile': profile, 'command': 'touch /tmp/escape'})
        for action, data in [('server.service', {'profile': 'server', 'service': 'jenkins;touch /tmp/escape'}),
                             ('jenkins.config', {'profile': 'ci', 'job': '../secrets'})]:
            with self.assertRaises(runtime.SandboxError): a.remote_request(CONFIG, action, data)

    def test_remote_reads_use_existing_ssh_config_without_forwarding_or_password_arguments(self):
        for action, data in [('server.status', {'profile': 'server'}),
                             ('postgres.rows', {'profile': 'db', 'table': 'items'}),
                             ('rabbitmq.queues', {'profile': 'queue'}),
                             ('jenkins.config', {'profile': 'ci', 'job': 'folder/job'})]:
            command, payload = a.remote_request(CONFIG, action, data)
            self.assertEqual(command[0], 'ssh')
            self.assertIn('ForwardAgent=no', command)
            self.assertIn('StrictHostKeyChecking=yes', command)
            self.assertEqual(command[-2], 'fixture')
            self.assertNotIn('password', ' '.join(command).lower())
        command, payload = a.remote_request(CONFIG, 'postgres.tables', {'profile': 'env'})
        self.assertEqual(json.loads(payload)['env_file'], '/srv/application.env')
        compile(a.REMOTE_POSTGRES, '<remote-postgres>', 'exec')
        self.assertNotIn('shell=True', a.REMOTE_POSTGRES)
        config={**CONFIG,'postgres':{'local':{'server':'server','local_env_file':'/local/application.env','url_key':'PIM_DATABASE_URL'}}}
        command,payload=a.remote_request(config,'postgres.tables',{'profile':'local'})
        self.assertEqual(command[0],sys.executable)
        self.assertEqual(json.loads(payload)['env_file'],'/local/application.env')
        self.assertNotIn('PIM_DATABASE_URL=', ' '.join(command))

    def test_local_services_require_explicit_development_loopback_profiles(self):
        for origin in ('http://10.0.0.60:8000', 'http://localhost:8000', 'https://127.0.0.1:8000', 'http://127.0.0.1:8000/proxy'):
            config = {'local_http': {'dev': {'development_only': True, 'origin': origin, 'paths': ['/']}}}
            with self.subTest(origin=origin), self.assertRaises((runtime.SandboxError, ValueError)):
                a.local_http(config, {'profile': 'dev'})
        config = {'local_http': {'dev': {'development_only': True, 'origin': 'http://127.0.0.1:1', 'paths': ['/api/local']}}}
        for path in ('//remote/path', '/api/local/../proxy', '/api/local/%2e%2e/proxy', '/other'):
            with self.assertRaises(runtime.SandboxError):a.local_http(config, {'profile': 'dev', 'path': path})

    def test_worker_webfetch_cannot_bypass_service_restrictions(self):
        for url in ('http://10.0.0.60:8080/job/Oslo/build?token=anything',
                    'https://jenkins.company.example/job/Oslo/build',
                    'http://127.0.0.1:18080', 'https://user:password@github.com'):
            with self.assertRaises(runtime.SandboxError): a.public_url({}, url)
        self.assertEqual(a.public_url({}, 'https://www.postgresql.org/docs/'), 'https://www.postgresql.org/docs/')

    def test_local_command_masks_control_and_credentials_and_checks_writable_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / '.env').write_text('SECRET=fixture')
            (root / '.opencode').mkdir()
            with patch.object(a.shutil, 'which', return_value='/usr/bin/bwrap'):
                argv = a.local_argv(root, {'command': 'echo test', '_scope': ['src'], '_exclusions': []})
                self.assertIn('--unshare-all', argv)
                self.assertIn('--clearenv', argv)
                self.assertIn(str(root / '.env'), argv)
                self.assertIn(str(root / '.opencode'), argv)
                for scope in ('../outside', '.opencode', '/tmp'):
                    with self.assertRaises(runtime.SandboxError):
                        a.local_argv(root, {'command': 'echo test', '_scope': [scope]})
                (root / 'link').symlink_to(root / 'src')
                with self.assertRaisesRegex(runtime.SandboxError, 'symlink'):
                    a.local_argv(root, {'command': 'echo test', '_scope': ['link']})
            with patch.object(a.shutil, 'which', return_value=None), self.assertRaisesRegex(runtime.SandboxError, 'never used as a fallback'):
                a.local_argv(root, {'command': 'echo test', '_scope': ['.']})


@unittest.skipUnless(os.environ.get('OPENCODE_TEST_ISOLATION') == '1', 'requires real local namespace/network permissions')
class LocalIsolationTests(unittest.TestCase):
    def test_worker_writes_scoped_source_but_cannot_read_host_credentials_or_connect_to_host_services(self):
        import socket
        with tempfile.TemporaryDirectory() as directory, socket.socket() as listener, socket.socket(socket.AF_UNIX) as unix:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / '.env').write_text('NEVER_EXPOSE_THIS')
            (root / '.opencode').mkdir()
            listener.bind(('127.0.0.1', 0));listener.listen()
            port = listener.getsockname()[1]
            unix.bind(str(root / 'host.sock'));unix.listen()
            script = ('import os,socket,pathlib\n'
                      'pathlib.Path("src/result.txt").write_text("local write")\n'
                      'try:\n assert not pathlib.Path(".env").read_text()\n'
                      'except PermissionError: pass\n'
                      'assert "BROKER_SECRET" not in os.environ\n'
                      'assert not pathlib.Path('+repr(str(Path.home() / '.ssh'))+').exists()\n'
                      's=socket.socket(); s.settimeout(.2)\n'
                      'assert s.connect_ex(("127.0.0.1",'+str(port)+')) != 0\n'
                      'u=socket.socket(socket.AF_UNIX); assert u.connect_ex("host.sock") != 0\n'
                      'inner=socket.socket(); inner.bind(("127.0.0.1",0)); inner.listen()\n'
                      'client=socket.socket(); assert client.connect_ex(inner.getsockname()) == 0\n'
                      'client.close(); inner.close()')
            argv = a.local_argv(root, {'command': 'python3 -c ' + shlex.quote(script), '_scope': ['src']})
            run = subprocess.run(argv, capture_output=True, text=True, env={**os.environ, 'BROKER_SECRET': 'NOT_VISIBLE'}, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual((root / 'src/result.txt').read_text(), 'local write')
            self.assertEqual((root / '.env').read_text(), 'NEVER_EXPOSE_THIS')
            run = subprocess.run(a.local_argv(root, {'command': 'touch outside-scope.txt', '_scope': ['src']}), capture_output=True, timeout=15)
            self.assertNotEqual(run.returncode, 0)
            self.assertFalse((root / 'outside-scope.txt').exists())

    def test_local_service_write_and_redirect_rejection(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                self.server.calls += 1
                self.send_response(200);self.end_headers();self.wfile.write(b'local write accepted')
            def do_GET(self):
                self.send_response(302);self.send_header('Location', 'http://10.0.0.60/');self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler);server.calls = 0
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        try:
            config = {'local_http': {'dev': {'development_only': True, 'origin': 'http://127.0.0.1:'+str(server.server_port), 'paths': ['/dev/']}}}
            result = a.local_http(config, {'profile': 'dev', 'path': '/dev/write', 'method': 'POST', 'body': {'test': True}})
            self.assertEqual(result['status'], 200);self.assertEqual(server.calls, 1)
            with self.assertRaisesRegex(runtime.SandboxError, 'redirect'):
                a.local_http(config, {'profile': 'dev', 'path': '/dev/redirect'})
        finally:
            server.shutdown();server.server_close();thread.join()
