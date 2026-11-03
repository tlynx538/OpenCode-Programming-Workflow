"""Project settings and Docker sandboxes owned by interactive OpenCode sessions."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import uuid

import runtime as b


def home(repo):
    return b.workspace_home(repo)


def settings_path(repo):
    return home(repo) / 'settings.json'


def validate(settings):
    b.require(isinstance(settings, dict) and settings.get('version') in (1, 2), 'Unsupported project settings version')
    b.require(isinstance(settings.get('policy'), dict), 'Project settings need a policy object')
    b.validate_tests(settings['policy'].get('tests'))
    config = settings.get('sandbox', {})
    b.require(isinstance(config, dict), 'Sandbox settings must be an object')
    b.require(set(config) <= {'docker', 'context', 'host', 'build', 'memory', 'cpus', 'pids_limit',
                              'tmpfs_size', 'shm_size', 'environment', 'prepare_commands'}, 'Unknown sandbox setting')
    executable = config.get('docker', 'docker')
    b.require(executable in ('docker', 'docker.exe', '/usr/local/bin/docker', '/usr/bin/docker',
                            '/opt/homebrew/bin/docker', '/Applications/Docker.app/Contents/Resources/bin/docker'),
              'Use docker on PATH or a standard Docker installation path')
    b.require(not (config.get('context') and config.get('host')), 'Choose Docker context or host, not both')
    for key in ('context', 'host'):
        value = config.get(key)
        b.require(value is None or (isinstance(value, str) and value and not value.startswith('-')
                                   and '\x00' not in value), f'Invalid Docker {key}')
    for key, default in (('memory', '2g'), ('tmpfs_size', '2g'), ('shm_size', '256m')):
        b.require(isinstance(config.get(key, default), str)
                  and re.fullmatch(r'[1-9][0-9]*[kmg]?', config.get(key, default)), f'Invalid {key}')
    b.require(type(config.get('cpus', 2)) in (int, float) and 0 < config.get('cpus', 2) <= 64, 'Invalid cpus')
    b.require(type(config.get('pids_limit', 512)) is int and 1 <= config.get('pids_limit', 512) <= 4096, 'Invalid pids_limit')
    environment = config.get('environment', {})
    b.require(isinstance(environment, dict) and all(isinstance(k, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k)
              and isinstance(v, str) and '\x00' not in v for k, v in environment.items()), 'Invalid sandbox environment')
    commands = config.get('prepare_commands', [])
    b.require(isinstance(commands, list) and all(isinstance(cmd, list) and cmd and all(
              isinstance(x, str) and x and '\x00' not in x for x in cmd) for cmd in commands), 'Invalid prepare_commands')
    build = config.get('build')
    if build is not None:
        b.require(isinstance(build, dict) and set(build) <= {'dockerfile', 'timeout_seconds'}, 'Invalid image build settings')
        b.require(isinstance(build.get('dockerfile'), str) and build['dockerfile'].strip(), 'Build recipe must contain Dockerfile text')
        b.require(type(build.get('timeout_seconds', 900)) is int and 1 <= build.get('timeout_seconds', 900) <= 3600,
                  'Invalid image build timeout')
        b.require('@' not in settings['policy']['tests']['image'], 'Build output needs a tag, not an image digest')
    return settings


def load(repo):
    path = settings_path(repo)
    return validate(json.loads(path.read_text())) if path.exists() else None


def save(repo, policy, config, version=2):
    value = validate({'version': version, 'policy': policy, 'sandbox': config})
    b.atomic_json(settings_path(repo), value)
    return value


def docker(config):
    command = [config.get('docker', 'docker')]
    for key in ('context', 'host'):
        if config.get(key):
            command += ['--' + key, config[key]]
    return command


def identity(settings):
    return b.digest({'sandbox': settings['sandbox'], 'image': settings['policy']['tests']['image']})


class SessionSandbox:
    def __init__(self, repo, session_id):
        b.require(isinstance(session_id, str) and 0 < len(session_id) <= 256, 'Session ID required')
        self.repo = Path(repo).resolve()
        self.session_id = session_id
        self.project = b.digest(str(home(repo)))[:16]
        self.key = b.digest(session_id)[:24]
        self.directory = home(repo) / 'sessions' / self.key
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'sandbox.json'
        self.ended = self.directory / 'ended'
        self.name = f'bdfl-session-{self.project}-{self.key}'

    @contextmanager
    def lock(self):
        path = self.directory / 'sandbox.lock'
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise b.SandboxError('Session sandbox is busy; retry after the current operation') from error
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            yield
        finally:
            path.unlink()

    def read(self):
        return json.loads(self.path.read_text()) if self.path.exists() else None

    def inspect(self, config):
        result = b.execute(docker(config) + ['container', 'inspect', self.name], timeout=15)
        return json.loads(result)[0]

    def owned(self, info):
        labels = info.get('Config', {}).get('Labels', {}) or {}
        b.require(labels.get('runtime.project') == self.project and labels.get('runtime.session') == self.key,
                  'Refusing to use or remove a container not owned by this project/session')

    def ensure(self, settings=None):
        settings = settings or load(self.repo)
        if settings is None:
            return {'status': 'needs_configuration', 'settings_file': str(settings_path(self.repo))}
        validate(settings)
        config = settings['sandbox']
        with self.lock():
            state = self.read()
            if state and state.get('config') is not None:
                if state['status'] == 'active' and not self.ended.exists():
                    b.require(state['settings_hash'] == identity(settings),
                              'Sandbox configuration changed; end this session sandbox before recreating it')
                previous_config = state['config']
                try:
                    info = self.inspect(previous_config)
                except b.SandboxError:
                    # Only recreate after Docker confirms the container is absent.
                    b.execute(docker(previous_config) + ['info', '--format', '{{.ServerVersion}}'], timeout=15)
                    names = b.execute(docker(previous_config) + ['ps', '-a', '--format', '{{.Names}}'], timeout=15).decode().splitlines()
                    b.require(self.name not in names, 'Cannot inspect the existing sandbox; refusing to recreate it')
                else:
                    self.owned(info)
                    if state['status'] == 'active' and not self.ended.exists() and info['State']['Running']:
                        return state
                    b.execute(docker(previous_config) + ['rm', '-f', self.name])
            self.ended.unlink(missing_ok=True)
            state = {'status': 'starting', 'session_id': self.session_id, 'container': self.name,
                     'settings_hash': identity(settings), 'config': config, 'generation': uuid.uuid4().hex}
            b.atomic_json(self.path, state)
            image = self.image(settings)
            b.require(not self.ended.exists(), 'Session ended during sandbox preparation')
            argv = docker(config) + ['run', '-d', '--name', self.name, '--pull=never', '--init',
                    '--label', 'runtime.project=' + self.project, '--label', 'runtime.session=' + self.key,
                    '--network=none', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                    '--pids-limit', str(config.get('pids_limit', 512)), '--memory', config.get('memory', '2g'),
                    '--cpus', str(config.get('cpus', 2)), '--user=65534:65534',
                    '--shm-size', config.get('shm_size', '256m'),
                    '--tmpfs', f"/tmp:rw,nosuid,nodev,size={config.get('tmpfs_size', '2g')},mode=1777",
                    '--workdir', '/tmp', '--entrypoint', '/bin/sh']
            environment = {'HOME': '/tmp', 'XDG_CACHE_HOME': '/tmp/.cache', **config.get('environment', {})}
            for key, value in environment.items():
                argv += ['--env', key + '=' + value]
            argv += [image, '-c', 'while :; do sleep 3600; done']
            b.execute(argv, timeout=60)
            state.update(status='active', image_id=image)
            # Persist immediately: cleanup can find a container even if later checks fail.
            b.atomic_json(self.path, state)
            if self.ended.exists():
                self.end()
                raise b.SandboxError('Session ended during sandbox startup')
            info = self.inspect(config)
            self.owned(info)
            b.require(info['State']['Running'], 'Session sandbox exited during startup')
            return state

    def image(self, settings):
        path = home(self.repo) / 'image-build.lock'
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise b.SandboxError('Another session is preparing the project image; retry shortly') from error
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return self._image(settings)
        finally:
            path.unlink()

    def _image(self, settings):
        config = settings['sandbox']
        tag = settings['policy']['tests']['image']
        build = config.get('build')
        cache = home(self.repo) / 'image-cache.json'
        fingerprint = None
        if build:
            # Build inputs include the eligible source and the recipe, never local secrets/dependencies.
            fingerprint = b.digest({'build': build, 'files': b.source_files(self.repo), 'tag': tag})
        cached = json.loads(cache.read_text()) if cache.exists() else {}
        try:
            image = b.execute(docker(config) + ['image', 'inspect', '--format', '{{.Id}}', tag], timeout=15).decode().strip()
        except b.SandboxError:
            image = None
        if image and (not build or cached.get(fingerprint) == image):
            return image
        b.require(build is not None, 'Test image is unavailable. Configure a project sandbox build recipe or an existing image.')
        with b.mirror(self.repo) as source:
            recipe = source / '.bdfl-sandbox.Dockerfile'
            b.require(not recipe.exists(), 'Reserved sandbox build filename exists in source')
            recipe.write_text(build['dockerfile'], encoding='utf-8')
            result = b.run_logged(docker(config) + ['build', '--tag', tag, '--file', str(recipe), str(source)],
                                  timeout=build.get('timeout_seconds', 900), cancelled=self.ended.exists)
            b.require(result.returncode == 0, 'Sandbox image build failed: ' + result.stderr.decode(errors='replace')[-4000:])
        image = b.execute(docker(config) + ['image', 'inspect', '--format', '{{.Id}}', tag], timeout=15).decode().strip()
        cached[fingerprint] = image
        b.atomic_json(cache, cached)
        return image

    def active(self, settings):
        state = self.read()
        b.require(not self.ended.exists() and state and state['status'] == 'active',
                  'Session sandbox has ended; resume the chat to recreate it')
        b.require(state['settings_hash'] == identity(settings), 'Frozen sandbox configuration no longer matches this session')
        return state

    def end(self):
        # Mark ended before cleanup, preventing workers from creating new containers.
        # Deliberately do not take the test lock: Docker removal must interrupt an active test.
        state = self.read()
        self.ended.touch()
        if state is None:
            return {'status': 'ended', 'session_id': self.session_id}
        if state['status'] == 'removed':
            return state
        state['status'] = 'ended'
        b.atomic_json(self.path, state)
        config = state['config']
        try:
            info = self.inspect(config)
        except b.SandboxError:
            b.execute(docker(config) + ['info', '--format', '{{.ServerVersion}}'], timeout=15)
            names = b.execute(docker(config) + ['ps', '-a', '--format', '{{.Names}}'], timeout=15).decode().splitlines()
            b.require(self.name not in names, 'Sandbox cleanup could not inspect the existing container')
        else:
            self.owned(info)
            b.execute(docker(config) + ['rm', '-f', self.name], timeout=30)
        state['status'] = 'removed'
        b.atomic_json(self.path, state)
        return state


class SessionDockerTests:
    """Reuse the session container, replacing its candidate workspace for every checkpoint."""
    def __init__(self, repo, session_id, settings):
        self.sandbox = SessionSandbox(repo, session_id)
        self.settings = validate(settings)

    def run(self, root, policy):
        b.require(policy == self.settings['policy'], 'Test policy differs from the frozen project settings')
        with self.sandbox.lock():
            state = self.sandbox.active(self.settings)
            config = self.settings['sandbox']
            prefix = docker(config) + ['exec', '--workdir', '/tmp/project', self.sandbox.name]
            records = []
            try:
                with b.mirror(root, agent=False) as source, tempfile.TemporaryFile() as archive:
                    with tarfile.open(fileobj=archive, mode='w') as tar:
                        for path in sorted(source.rglob('*')):
                            if path.is_file():
                                tar.add(path, arcname=path.relative_to(source).as_posix(), recursive=False)
                    archive.seek(0)
                    argv = docker(config) + ['exec', '-i', self.sandbox.name, '/bin/sh', '-c',
                            'rm -rf /tmp/project && mkdir /tmp/project && tar --no-same-owner -xf - -C /tmp/project']
                    copied = b.capture(argv, stdin=archive, timeout=60)
                    b.require(copied.returncode == 0, 'Sandbox source transfer failed: ' + copied.stderr.decode(errors='replace')[-4000:])
                for command in config.get('prepare_commands', []) + policy['tests']['commands']:
                    self.sandbox.active(self.settings)
                    result = b.run_logged(prefix + command, timeout=policy['tests']['timeout_seconds'])
                    records.append({'argv': command, 'exit_code': result.returncode,
                                    'stdout': result.stdout.decode(errors='replace')[-100000:],
                                    'stderr': result.stderr.decode(errors='replace')[-100000:]})
                    if result.returncode:
                        break
            except subprocess.TimeoutExpired as error:
                # docker exec timeout alone can leave a test process alive; remove its whole sandbox.
                self.sandbox.end()
                records.append({'argv': list(error.cmd) if isinstance(error.cmd, list) else [str(error.cmd)],
                                'exit_code': 124, 'stdout': '', 'stderr': 'Sandbox test/transfer timeout; container removed'})
            except OSError as error:
                self.sandbox.end()
                raise b.SandboxError(f'Session Docker runner unavailable; no host fallback: {error}') from error
            except BaseException:
                self.sandbox.end()
                raise
            return {'passed': bool(records) and all(record['exit_code'] == 0 for record in records), 'records': records}
