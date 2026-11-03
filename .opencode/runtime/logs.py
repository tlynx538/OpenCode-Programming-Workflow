"""Durable command logs and read-only followers for OpenCode's native shell panel."""
from contextlib import contextmanager, redirect_stderr
import json
import re
import sys
import threading
import time

import runtime as b


def operation_directory(repo, operation_id):
    b.require(isinstance(operation_id, str) and re.fullmatch(r'[a-f0-9]{32}', operation_id), 'Invalid log operation ID')
    return b.workspace_home(repo) / 'operations' / operation_id


@contextmanager
def operation(repo, payload):
    operation_id = payload.get('operation_id')
    if operation_id is None:
        yield
        return
    directory = operation_directory(repo, operation_id)
    directory.mkdir(parents=True, exist_ok=False)
    state = directory / 'state.json'
    b.atomic_json(state, {'finished': False, 'action': payload.get('action')})
    original = sys.stderr
    lock = threading.Lock()
    with (directory / 'output.log').open('w', encoding='utf-8') as file:
        class Tee:
            def write(self, text):
                with lock:
                    file.write(text)
                    file.flush()
                    original.write(text)
                    original.flush()
                return len(text)

            def flush(self):
                file.flush()
                original.flush()

        with redirect_stderr(Tee()):
            failed = False
            error_text = None
            try:
                print(f"Poseidon {payload.get('action')}: preparing workspace operation", file=sys.stderr, flush=True)
                yield
            except BaseException as error:
                failed = True
                error_text = str(error) or type(error).__name__
                print(f'Poseidon operation stopped: {error}', file=sys.stderr, flush=True)
                raise
            else:
                print('Poseidon operation completed', file=sys.stderr, flush=True)
            finally:
                b.atomic_json(state, {'finished': True, 'failed': failed, 'error': error_text, 'action': payload.get('action')})


def follow(repo, identifier, output=None, poll_seconds=0.2):
    """Follow one validated operation log without launching work."""
    output = output or sys.stdout.buffer
    directory = operation_directory(repo, identifier)
    path = directory / 'output.log'
    def finished():
        state = directory / 'state.json'
        return state.exists() and json.loads(state.read_text()).get('finished', False)
    deadline = time.monotonic() + 10
    while not path.exists():
        if finished():
            return
        b.require(time.monotonic() < deadline, 'Log producer did not start; the follower did not launch any work')
        time.sleep(poll_seconds)
    with path.open('rb') as file:
        # Show recent context on attach, with the complete log retained on disk.
        size = path.stat().st_size
        file.seek(max(0, size - 65536))
        if size > 65536:
            output.write(b'[Earlier output omitted from preview; full log remains on disk]\n')
        while True:
            data = file.read(65536)
            if data:
                output.write(data)
                output.flush()
                continue
            if finished():
                # The producer records completion after its final write.
                data = file.read()
                if data:
                    output.write(data)
                    output.flush()
                break
            time.sleep(poll_seconds)
    state = json.loads((directory / 'state.json').read_text())
    b.require(not state.get('failed'), 'Workspace operation failed: ' + str(state.get('error')))
