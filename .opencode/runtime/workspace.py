#!/usr/bin/env python3
"""Sandbox/settings/test tools for native agents. No agent orchestration or authorization protocol."""
import argparse
from datetime import datetime, timezone
import json
import os
import threading
import time
from pathlib import Path
import signal
import subprocess
import sys
import uuid

import runtime
import logs
import sandbox


def dispatch(root, payload):
    action = payload.get('action')
    settings = sandbox.load(root)
    session = sandbox.SessionSandbox(root, payload.get('session_id'))
    if action == 'settings':
        example = json.loads((runtime.BUNDLE / 'runtime/settings.example.json').read_text())
        return {'settings': settings, 'settings_file': str(sandbox.settings_path(root)),
                'runtime': str(Path(__file__).resolve()), 'repo': str(root), 'session_id': session.session_id,
                'tests_template': example['policy']['tests'], 'sandbox_template': example['sandbox']}
    if action == 'status':
        latest = sandbox.home(root) / 'latest-test.json'
        return {'sandbox': session.read(), 'settings_file': str(sandbox.settings_path(root)),
                'latest_test': json.loads(latest.read_text()) if latest.exists() else None}
    if action == 'end_sandbox':
        return session.end()
    if action == 'session_start':
        try:
            return session.ensure(settings)
        except (runtime.SandboxError, OSError, ValueError, subprocess.TimeoutExpired) as error:
            return {'status': 'unavailable', 'error': str(error), 'settings_file': str(sandbox.settings_path(root))}
    if action == 'configure':
        tests = payload.get('tests', settings['policy']['tests'] if settings else None)
        config = payload.get('sandbox', settings['sandbox'] if settings else {})
        settings = sandbox.save(root, {'tests': runtime.validate_tests(tests)}, config, version=2)
        return {'settings_file': str(sandbox.settings_path(root)), 'sandbox': session.ensure(settings)}
    runtime.require(action == 'test', 'Unknown workspace action')
    runtime.require(settings is not None, 'Configure project sandbox/test settings first')
    session.ensure(settings)
    before = runtime.fingerprint(root)
    result = sandbox.SessionDockerTests(root, session.session_id, settings).run(root, settings['policy'])
    stale = runtime.fingerprint(root) != before
    result.update(passed=result['passed'] and not stale, candidate=before, stale=stale,
                  settings_hash=runtime.digest(settings), session_id=session.session_id,
                  timestamp=datetime.now(timezone.utc).isoformat())
    evidence = sandbox.home(root) / 'evidence'
    evidence.mkdir(exist_ok=True)
    identifier = payload.get('operation_id', uuid.uuid4().hex)
    runtime.require(isinstance(identifier, str) and len(identifier) == 32 and all(c in '0123456789abcdef' for c in identifier), 'Invalid evidence ID')
    path = evidence / (identifier + '.json')
    result['evidence_file'] = str(path)
    runtime.atomic_json(path, result)
    runtime.atomic_json(sandbox.home(root) / 'latest-test.json', result)
    print('Tests ' + ('PASSED' if result['passed'] else 'FAILED') + ('; source changed during validation' if stale else ''), file=sys.stderr, flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('mode', choices=('call', 'follow-operation', 'state-home'))
    parser.add_argument('identifier', nargs='?')
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin) if args.mode == 'call' else None
        requested_root = args.repo.resolve()
        root = runtime.repository_root(requested_root) or requested_root
        if args.mode == 'state-home':
            print(json.dumps({'directory': str(runtime.workspace_home(root))}))
            return 0
        if args.mode != 'call':
            logs.follow(root, args.identifier)
            return 0
        if payload.get('action') in ('session_start', 'configure', 'test'):
            payload.setdefault('operation_id', uuid.uuid4().hex)
        with logs.operation(root, payload):
            result = dispatch(root, payload)
            if payload.get('operation_id'):
                result['operation_id'] = payload['operation_id']
            print(json.dumps(result))
        return 0
    except KeyboardInterrupt:
        print(json.dumps({'error': 'Workspace operation interrupted; project work is preserved'}))
        return 130
    except (runtime.SandboxError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error)}))
        return 1


if __name__ == '__main__':
    # Only detached, governor-owned group leaders install an orphan watchdog.
    # A plugin/server crash must not strand the helper and its same-group children.
    if os.name == 'posix' and os.getpgrp() == os.getpid():
        owner = os.getppid()
        def watch_owner():
            while os.getppid() == owner and owner != 1:
                time.sleep(1)
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(3)
            os.killpg(os.getpgrp(), signal.SIGKILL)
        threading.Thread(target=watch_owner, daemon=True).start()
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    sys.exit(main())
