#!/usr/bin/env python3
"""Role-aware server observations and network-isolated local development commands."""
from __future__ import annotations
import argparse
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

import runtime

ROLES = {'poseidon', 'team-lead', 'maintainer', 'researcher', 'coder', 'reviewer'}
CONFIG = Path(os.environ.get('OPENCODE_SYSTEM_ACCESS_CONFIG', Path.home() / '.config/opencode/system-access.json'))
KINDS = ('servers', 'postgres', 'mysql', 'rabbitmq', 'jenkins', 'local_http')


def require(ok, text):
    runtime.require(ok, text)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$]{0,62}', value), 'Invalid SQL identifier')
    return value


def bounded(value, default, maximum):
    value = default if value is None else value
    require(type(value) is int and 1 <= value <= maximum, 'Invalid result limit')
    return value


def load():
    if not CONFIG.exists():
        return {'version': 1, **{kind: {} for kind in KINDS}}
    value = json.loads(CONFIG.read_text())
    require(value.get('version') == 1, 'Unsupported system access configuration')
    return value


def profile(config, kind, name):
    require(isinstance(name, str) and name in config.get(kind, {}), 'Configure the named ' + kind + ' connection profile first')
    return config[kind][name]


def ssh_argv(config, server, command):
    connection = profile(config, 'servers', server)
    alias = connection['ssh']
    require(isinstance(alias, str) and re.fullmatch(r'[A-Za-z0-9_.-]+', alias) and not alias.startswith('-'), 'Invalid SSH alias')
    return ['ssh', '-F', str(Path.home() / '.ssh/config'), '-T', '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=yes', '-o', 'ForwardAgent=no',
            '-o', 'ClearAllForwardings=yes', '-o', 'PermitLocalCommand=no', alias, command]


def sql_query(kind, operation, data):
    """Generate observation-only SQL; never accept raw SQL or client metacommands."""
    limit = bounded(data.get('limit'), 50, 200)
    if operation == 'tables':
        sql = "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema','mysql','performance_schema','sys') ORDER BY table_schema, table_name"
    elif operation == 'columns':
        schema, table = identifier(data.get('schema', 'public')), identifier(data.get('table'))
        sql = f"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = '{schema}' AND table_name = '{table}' ORDER BY ordinal_position"
    else:
        require(operation == 'rows', 'Unsupported SQL observation')
        schema, table = identifier(data.get('schema', 'public')), identifier(data.get('table'))
        quote = '"' if kind == 'postgres' else '`'
        columns = data.get('columns', [])
        require(isinstance(columns, list) and len(columns) <= 50, 'Invalid result columns')
        selected = ', '.join(quote + identifier(column) + quote for column in columns) if columns else '*'
        sql = f'SELECT {selected} FROM {quote}{schema}{quote}.{quote}{table}{quote}'
        filters = data.get('filters', {})
        require(isinstance(filters, dict) and len(filters) <= 20, 'Invalid equality filters')
        terms = []
        def literal(value):
            require(type(value) in (str, int, float, bool) and (type(value) is not float or math.isfinite(value)), 'Filters must contain scalar values')
            text = str(value).lower() if type(value) is bool else str(value)
            require(len(text) <= 4096, 'Filter value too large')
            encoded = text.encode().hex()
            return f"convert_from(decode('{encoded}','hex'),'UTF8')" if kind == 'postgres' else f"CONVERT(X'{encoded}' USING utf8mb4)"
        for column, value in filters.items():
            name = quote + identifier(column) + quote
            if value is None:
                terms.append(name + ' IS NULL')
            else:
                cast = 'TEXT' if kind == 'postgres' else 'CHAR'
                if isinstance(value, list):
                    require(0 < len(value) <= 50, 'Filter lists need 1..50 scalar values')
                    terms.append(f'CAST({name} AS {cast}) IN (' + ','.join(literal(v) for v in value) + ')')
                else:
                    terms.append(f'CAST({name} AS {cast}) = ' + literal(value))
        if terms: sql += ' WHERE ' + ' AND '.join(terms)
    sql += f' LIMIT {limit};'
    if kind == 'postgres':
        return 'BEGIN READ ONLY; SET LOCAL statement_timeout = 15000; ' + sql + ' ROLLBACK;'
    return 'SET SESSION TRANSACTION READ ONLY; START TRANSACTION; ' + sql + ' ROLLBACK;'


# Runs locally or on the selected SSH server; URL values never appear in arguments or results.
REMOTE_POSTGRES = '''import os,sys,json,urllib.parse,subprocess,shlex
p=json.load(sys.stdin)
values={}
for line in open(p['env_file']):
 line=line.strip()
 if not line or line.startswith('#') or '=' not in line:continue
 key,value=line.removeprefix('export ').split('=',1)
 values[key.strip()]=value.strip().strip("\\\"'")
u=urllib.parse.urlsplit(values[p['url_key']].replace('postgresql+psycopg://','postgresql://').replace('postgresql+psycopg2://','postgresql://'))
if u.scheme.split('+',1)[0] not in ('postgres','postgresql'):raise SystemExit('Expected a PostgreSQL connection')
env={**os.environ,'PGHOST':u.hostname or 'localhost','PGPORT':str(u.port or 5432),'PGUSER':urllib.parse.unquote(u.username or ''),'PGPASSWORD':urllib.parse.unquote(u.password or ''),'PGDATABASE':urllib.parse.unquote(u.path.lstrip('/')),'PGCONNECT_TIMEOUT':'8','PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=15000'}
r=subprocess.run(['psql','-X','--csv','-v','ON_ERROR_STOP=1','-c',p['sql']],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
sys.stdout.buffer.write(r.stdout[:262144]);sys.stderr.buffer.write(r.stderr[:4096]);sys.exit(r.returncode)
'''


def remote_request(config, action, data):
    require(isinstance(action, str), 'System action required')
    kind, _, operation = action.partition('.')
    if kind == 'server':
        server = data.get('profile')
        if operation == 'status':
            command = 'hostname; uptime; df -h'
        elif operation == 'processes':
            command = 'ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -81'
        elif operation == 'containers':
            command = 'docker ps --format ' + shlex.quote('{{.Names}} {{.Image}} {{.Status}}')
        else:
            require(operation in ('service', 'logs'), 'Unsupported server observation')
            unit = data.get('service')
            require(isinstance(unit, str) and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]{0,100}', unit), 'Invalid systemd service')
            command = shlex.join(['systemctl', '--no-pager', '--lines=40', 'status', unit] if operation == 'service'
                                 else ['journalctl', '--no-pager', '-n', '100', '-u', unit])
        return ssh_argv(config, server, command), None
    require(kind in ('postgres', 'mysql', 'rabbitmq', 'jenkins'), 'Unsupported remote read operation')
    connection = profile(config, kind, data.get('profile'))
    server = connection['server']
    if kind == 'postgres' and (connection.get('env_file') or connection.get('local_env_file')):
        require(operation in ('tables', 'columns', 'rows'), 'Unsupported PostgreSQL observation')
        payload = {'env_file': connection.get('local_env_file', connection.get('env_file')), 'url_key': connection.get('url_key', 'DATABASE_URL'),
                   'sql': sql_query(kind, operation, data)}
        if connection.get('local_env_file'):
            return [sys.executable, '-c', REMOTE_POSTGRES], json.dumps(payload)
        prefix = ['sudo', '-n', 'python3'] if connection.get('sudo', False) else ['python3']
        return ssh_argv(config, server, shlex.join(prefix + ['-c', REMOTE_POSTGRES])), json.dumps(payload)
    if kind in ('postgres', 'mysql'):
        sql = sql_query(kind, operation, {**data, 'schema': data.get('schema', 'public' if kind == 'postgres' else connection['database'])})
        command = ['psql', '-X', '--csv', '-v', 'ON_ERROR_STOP=1', '-d', identifier(connection['database']), '-c', sql] if kind == 'postgres' else ['mysql', '--no-defaults', '--batch', '--raw', '--database', identifier(connection['database']), '--execute', sql]
        if connection.get('container'):
            command = ['docker', 'exec', connection['container']] + command
        elif connection.get('sudo_user'):
            command = ['sudo', '-n', '-u', connection['sudo_user']] + command
    elif kind == 'rabbitmq':
        commands = {'status': ['status'], 'queues': ['list_queues', 'name', 'messages', 'consumers', 'state'],
                    'exchanges': ['list_exchanges', 'name', 'type'], 'bindings': ['list_bindings'], 'vhosts': ['list_vhosts', 'name']}
        require(operation in commands, 'RabbitMQ observation only; publishing, consuming, acknowledgments, purging and configuration are forbidden')
        command = ['rabbitmqctl', '-q', '-p', connection.get('vhost', '/')] + commands[operation]
        if connection.get('container'):
            command = ['docker', 'exec', connection['container']] + command
        if connection.get('sudo', False):
            command = ['sudo', '-n'] + command
    else:
        require(operation in ('jobs', 'config', 'build', 'log'), 'Jenkins observation only; builds, script console, replay and configuration writes are forbidden')
        home = connection.get('home', '/var/lib/jenkins')
        if operation == 'jobs':
            command = ['find', home + '/jobs', '-maxdepth', '4', '-name', 'config.xml', '-print']
        else:
            job = data.get('job')
            require(isinstance(job, str) and all(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_. -]{0,100}', p) for p in job.split('/')), 'Invalid Jenkins job')
            directory = home + '/jobs/' + '/jobs/'.join(job.split('/'))
            if operation == 'config':
                filename = directory + '/config.xml'
            else:
                build = data.get('build')
                require(type(build) is int and build > 0, 'Numeric Jenkins build ID required')
                filename = directory + f'/builds/{build}/' + ('log' if operation == 'log' else 'build.xml')
            command = ['head', '-c', '262144', filename]
        if connection.get('sudo', False):
            command = ['sudo', '-n'] + command
    return ssh_argv(config, server, shlex.join(command)), None


def protected(relative):
    parts = relative.parts
    return any(p in runtime.CONTROL or p in ('.ssh', '.aws', '.gnupg') for p in parts) or runtime.secret(relative.as_posix()) or any('credentials' in p.lower() for p in parts)


def local_argv(root, data):
    require(sys.platform.startswith('linux') and shutil.which('bwrap'), 'Local commands require Linux bubblewrap; unrestricted shell is never used as a fallback')
    root = Path(root).resolve()
    home = Path.home()
    trusted = [home/'.ssh', home/'.config/opencode', home/'.codex', home/'.agents', home/'.local/share/opencode', home/'.local/state/opencode']
    require(root.is_dir() and str(root) not in ('/', str(home)) and not any(root == p or p in root.parents for p in trusted), 'Use a development workspace, never host credentials or agent control storage')
    command = data.get('command')
    require(isinstance(command, str) and 0 < len(command) <= 16000 and '\x00' not in command, 'Local command required')
    scope = data.get('_scope')
    require(isinstance(scope, list) and scope, 'Trusted assignment scope required')
    argv = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--clearenv']
    for name in ('/usr', '/bin', '/sbin', '/lib', '/lib64'):
        if Path(name).exists(): argv += ['--ro-bind', name, name]
    argv += ['--dir', '/etc']
    for name in ('/etc/ld.so.cache', '/etc/passwd', '/etc/group'):
        if Path(name).exists(): argv += ['--ro-bind', name, name]
    argv += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--ro-bind', str(root), str(root)]
    for name in scope:
        rel = Path(name)
        require(name == '.' or (not rel.is_absolute() and '..' not in rel.parts and not protected(rel)), 'Unsafe writable scope')
        require(not any(root.joinpath(*rel.parts[:i]).is_symlink() for i in range(1, len(rel.parts)+1)), 'Writable scope must not contain symlinks')
        target = (root / rel).resolve()
        require(target == root or root in target.parents, 'Writable scope escapes workspace')
        require(target.exists(), 'Create named new files through native edit before running local commands')
        argv += ['--bind', str(target), str(root / rel)]
    # Mask credentials/control files after writable mounts; no host HOME, sockets or environment.
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in list(dirs) + files:
            candidate = Path(directory) / name
            rel = candidate.relative_to(root)
            if protected(rel) or candidate.is_socket() or candidate.is_fifo() or any(rel == Path(p) or Path(p) in rel.parents for p in data.get('_exclusions', [])):
                if candidate.is_symlink():
                    raise runtime.SandboxError('Protected symlink is unsupported in local development commands')
                argv += ['--tmpfs', str(candidate)] if candidate.is_dir() else ['--ro-bind', '/dev/null', str(candidate)]
                if name in dirs: dirs.remove(name)
        dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
    argv += ['--chdir', str(root), '--setenv', 'PATH', '/usr/local/bin:/usr/bin:/bin', '--setenv', 'HOME', '/tmp', '--setenv', 'LANG', 'C.UTF-8', '/bin/sh', '-c', command]
    return argv


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise runtime.SandboxError('Local development requests do not follow redirects')


def local_http(config, data):
    connection = profile(config, 'local_http', data.get('profile'))
    require(connection.get('development_only') is True, 'Explicit development-only local service profile required')
    origin = connection['origin']
    parsed = urllib.parse.urlsplit(origin)
    require(parsed.scheme == 'http' and parsed.path in ('', '/') and not parsed.query and not parsed.fragment and not parsed.username and parsed.hostname and ipaddress.ip_address(parsed.hostname).is_loopback,
            'Local service origin must be an HTTP loopback IP, never a hostname/proxy')
    path = data.get('path', '/')
    require(isinstance(path, str) and path.startswith('/') and not path.startswith('//') and not urllib.parse.urlsplit(path).scheme, 'Invalid local service path')
    decoded = urllib.parse.unquote(path).split('?', 1)[0]
    require('..' not in decoded.split('/') and '\\' not in decoded, 'Local service traversal is forbidden')
    require(any(path.startswith(prefix) for prefix in connection.get('paths', [])), 'Path is outside the configured local development service')
    method = data.get('method', 'GET')
    require(method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'), 'Unsupported local HTTP method')
    request = urllib.request.Request(origin.rstrip('/') + path, data=json.dumps(data['body']).encode() if 'body' in data else None,
                                     headers={'Content-Type': 'application/json'}, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=15) as response:
        return {'status': response.status, 'output': response.read(262145).decode(errors='replace')[:262144]}


PUBLIC_READ_HOSTS = ('www.postgresql.org', 'www.rabbitmq.com', 'www.jenkins.io', 'developer.mozilla.org',
                     'docs.python.org', 'react.dev', 'fastapi.tiangolo.com', 'opencode.ai',
                     'dev.opencode.ai', 'docs.opencode.ai', 'github.com', 'raw.githubusercontent.com',
                     'en.wikipedia.org', 'example.com')


def public_url(config, url):
    parsed = urllib.parse.urlsplit(url)
    hosts = config.get('public_read_hosts', PUBLIC_READ_HOSTS)
    require(parsed.scheme == 'https' and not parsed.username and not parsed.password and parsed.port in (None, 443)
            and parsed.hostname in hosts, 'Worker web fetch is restricted to approved public read-only sites; use system_access for infrastructure')
    return url


def public_fetch(config, data):
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, file, code, message, headers, newurl):
            public_url(config, newurl)
            return super().redirect_request(request, file, code, message, headers, newurl)
    url = public_url(config, data.get('url', ''))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirect())
    with opener.open(url, timeout=15) as response:
        raw = response.read(262145)
        return {'url': url, 'output': raw[:262144].decode(errors='replace'), 'truncated': len(raw)>262144}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--agent', required=True, choices=sorted(ROLES))
    args = parser.parse_args(argv)
    try:
        data = json.load(sys.stdin)
        config = load()
        action = data.get('action')
        if action == 'connections':
            result = {kind: list(config.get(kind, {})) for kind in KINDS}
            result['public_read_hosts'] = list(config.get('public_read_hosts', PUBLIC_READ_HOSTS))
        elif action == 'local_command':
            timeout = bounded(data.get('timeout_seconds'), 60, 300)
            command = local_argv(args.repo, data)
            run = runtime.capture(command, timeout=timeout, limit=262144)
            result = {'exit_code': run.returncode, 'output': run.stdout.decode(errors='replace'), 'stderr': run.stderr.decode(errors='replace'), 'network': 'isolated'}
        elif action == 'public_fetch':
            result = public_fetch(config, data)
        elif action == 'local_http':
            result = local_http(config, data)
        else:
            command, payload = remote_request(config, action, data)
            import tempfile
            with tempfile.TemporaryFile() as source:
                if payload is not None: source.write(payload.encode());source.seek(0)
                run = runtime.capture(command, timeout=35, stdin=source, limit=262144)
            require(run.returncode == 0, 'Remote read operation failed: ' + run.stderr.decode(errors='replace')[-4000:])
            result = {'output': run.stdout.decode(errors='replace'), 'access': 'remote-read-only', 'truncated': len(run.stdout) >= 262144}
        print(json.dumps(result))
        return 0
    except KeyboardInterrupt:
        print(json.dumps({'error': 'System operation interrupted'}));return 130
    except (runtime.SandboxError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error)}));return 1


if __name__ == '__main__':
    import signal
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    sys.exit(main())
