"""Bounded live OpenCode evaluation; does not change providers or permissions."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def api(method, path, payload=None):
    args = ['opencode', 'api', method, path]
    if payload is not None:
        args += ['--data', json.dumps(payload)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout[:1000])
    return json.loads(result.stdout) if result.stdout.strip() else None


def fingerprint(root):
    result = {}
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if (Path(directory) / d).relative_to(root).as_posix() != '.opencode/workspace'
                   and d not in {'.git', 'node_modules', '__pycache__',
                                                '.pytest_cache', 'dist', 'test-results'}
                   and not (Path(directory) / d).is_symlink()]
        for name in files:
            path = Path(directory) / name
            if path.is_symlink():
                continue
            total += path.stat().st_size
            if len(result) >= 2000 or total > 16 * 1024 * 1024:
                raise RuntimeError('Fixture exceeds evaluation source budget')
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--agent', required=True)
    parser.add_argument('--assignment', type=Path, help='Operator contract JSON for a disposable updated-bundle evaluation')
    parser.add_argument('--session', help='Reuse an idle evaluation session at the same location')
    parser.add_argument('--prompt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--tools', type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 300 or not 1 <= args.tools <= 20:
        parser.error('Use timeout 1..300 seconds and tools 1..20')
    root = args.directory.resolve()
    before = fingerprint(root)
    created = (api('GET', '/api/session/' + args.session)['data'] if args.session else
               api('POST', '/api/session', {'location': {'directory': str(root)},
                   'agent': args.agent, 'title': 'Bounded evaluation: ' + args.prompt.stem})['data'])
    session = created['id']
    if Path(created['location']['directory']).resolve() != root:
        raise RuntimeError('Evaluation location mismatch; no prompt sent')
    if created.get('agent') != args.agent:
        raise RuntimeError('Evaluation agent mismatch; no prompt sent')
    started = time.monotonic()
    previous_idle = created.get('time', {}).get('idle', 0)
    result = {'session': session, 'agent': args.agent, 'directory': str(root),
              'timeout': args.timeout, 'tool_budget': args.tools}
    tools, texts, errors = [], [], []
    try:
        if args.assignment:
            api('POST', f'/api/session/{session}/command', {'name':'agent-evaluate','text':args.assignment.read_text()})
        api('POST', f'/api/session/{session}/prompt', {'text': args.prompt.read_text()})
        while True:
            info = api('GET', f'/api/session/{session}')['data']
            messages = api('GET', f'/api/session/{session}/message?limit=100&order=asc')
            tools, texts, errors = [], [], []
            for message in messages['data']:
                if message.get('error'):
                    errors.append(message['error'])
                for part in message.get('content', []):
                    if part.get('type') == 'text':
                        texts.append(part.get('text', ''))
                    if part.get('type') == 'tool':
                        state = part.get('state', {})
                        tools.append({'name': part.get('name'), 'status': state.get('status'),
                                      'input': state.get('input'), 'error': state.get('error'),
                                      'output': str(state.get('output', state.get('content', '')))[:5000]})
            result['metrics'] = {'tool_attempts':len(tools),'completed_tool_calls':sum(t['status']=='completed' for t in tools),'tool_errors':sum(t['status']=='error' for t in tools),'assistant_words':sum(len(t.split()) for t in texts)}
            if len(tools) > args.tools:
                result['stopped'] = 'tool budget exceeded'
                break
            if info.get('outcome') and info.get('time', {}).get('idle', 0) > previous_idle:
                result['outcome'] = info['outcome']
                result['tokens'] = info.get('tokens')
                break
            if time.monotonic() - started > args.timeout:
                result['stopped'] = 'deadline exceeded'
                break
            time.sleep(1)
    except Exception as error:
        result['infrastructure_error'] = str(error)
    finally:
        # A client timeout must not leave server-side generation running.
        try:
            interrupted = api('POST', f'/api/session/{session}/interrupt')
            result['interrupt'] = interrupted
        except Exception as error:
            result['cleanup_error'] = str(error)
        if args.assignment:
            try:
                api('POST', f'/api/session/{session}/command', {'name':'agent-export','text':''})
                key = hashlib.sha256(json.dumps(session, separators=(',', ':')).encode()).hexdigest()
                helper = Path(__file__).resolve().parents[2] / '.opencode/runtime/workspace.py'
                state = subprocess.run([sys.executable, str(helper), '--repo', str(root), 'state-home'],
                                       capture_output=True, text=True, timeout=30, check=True)
                evidence = Path(json.loads(state.stdout)['directory']) / 'agent-evals' / (key + '.json')
                result['contract_evidence'] = json.loads(evidence.read_text())
            except Exception as error:
                result['contract_export_error'] = str(error)
        after = fingerprint(root)
        result.update(seconds=round(time.monotonic() - started, 2), tools=tools,
                      text=texts, errors=errors, before=before, after=after,
                      changed_files=sorted(k for k in before.keys() | after.keys()
                                           if before.get(k) != after.get(k)))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({k: result[k] for k in ['session', 'agent', 'outcome', 'stopped',
                         'infrastructure_error', 'seconds', 'changed_files'] if k in result}))
        print('Tool calls:', len(tools))
        for text in texts:
            print(text)
    # A successful agent turn is not a passing behavioral evaluation; grade separately.
    return 0 if result.get('outcome') == 'succeeded' and not result.get('stopped') else 1


if __name__ == '__main__':
    raise SystemExit(main())
