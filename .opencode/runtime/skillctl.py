#!/usr/bin/env python3
"""Validate and synchronize pinned native skills without executing upstream code."""
from __future__ import annotations

import argparse
import base64
from datetime import date
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile

BUNDLE = Path(__file__).resolve().parent.parent
MANIFEST = 'skills/SOURCES.json'
ROLES = {'poseidon', 'team-lead', 'maintainer', 'researcher', 'coder', 'reviewer'}


class SkillError(RuntimeError):
    pass


def need(condition, message):
    if not condition:
        raise SkillError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode()


def relative(value):
    need(isinstance(value, str) and value and '\\' not in value and ':' not in value
         and not any(c in value for c in '\x00\r\n') and not PurePosixPath(value).is_absolute()
         and all(p not in ('', '.', '..') for p in value.split('/')), f'Unsafe relative path: {value}')
    return value


def local(bundle, name):
    relative(name)
    path = bundle / name
    need(path.resolve().is_relative_to(bundle.resolve()), f'Path escapes bundle: {name}')
    need(not any(bundle.joinpath(*PurePosixPath(name).parts[:i]).is_symlink()
                 for i in range(1, len(PurePosixPath(name).parts) + 1)), f'Symlink in bundle: {name}')
    return path


def load_manifest(bundle=BUNDLE):
    value = json.loads((bundle / MANIFEST).read_text(encoding='utf-8'))
    need(value.get('schemaVersion') == 1, 'Unsupported skill manifest version')
    return value


def units(manifest):
    return manifest['skills'] + manifest.get('resources', [])


def inventory(directory):
    if not directory.exists():
        return {}
    result = {}
    for path in directory.rglob('*'):
        need(not path.is_symlink(), f'Symlink in managed directory: {path}')
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = path.read_bytes()
    return result


def frontmatter(data):
    """Read discovery fields from the restricted YAML forms used by pinned skills.

    OpenCode remains the authoritative full YAML parser. This deliberately rejects
    ambiguous discovery fields rather than trying to implement general YAML.
    """
    text = data.decode('utf-8')
    lines = text.splitlines()
    need(lines and lines[0] == '---', 'Missing YAML frontmatter')
    try:
        end = lines.index('---', 1)
    except ValueError as e:
        raise SkillError('Unterminated YAML frontmatter') from e
    fields = {}
    i = 1
    while i < end:
        match = re.match(r'^([a-zA-Z][\w/-]*):(?:\s+(.*))?$', lines[i])
        if match:
            key, value = match[1], match[2] or ''
            need(key not in fields, f'Duplicate frontmatter key: {key}')
            if value in ('>', '>-', '|', '|-'):
                block = []
                while i + 1 < end and (lines[i+1].startswith(' ') or not lines[i+1]):
                    i += 1
                    block.append(lines[i].strip())
                value = (' ' if value.startswith('>') else '\n').join(block)
            elif value.startswith('"'):
                try:
                    value = json.loads(value)
                except ValueError as e:
                    raise SkillError(f'Invalid quoted discovery field: {key}') from e
            elif value.startswith("'"):
                need(value.endswith("'"), 'Invalid quoted YAML value')
                value = value[1:-1].replace("''", "'")
            fields[key] = value
        i += 1
    need(isinstance(fields.get('name'), str) and fields['name'].strip(), 'Skill name is missing')
    need(isinstance(fields.get('description'), str) and fields['description'].strip(), 'Skill description is missing')
    return fields


def patches_for(unit, bundle):
    if not unit.get('patch'):
        return []
    data = local(bundle, unit['patch']).read_bytes()
    need(sha(data) == unit['patchSha256'], f'Unresolved local compatibility patch change: {unit.get("skill")}')
    return json.loads(data)


def patched(files, patches):
    result = dict(files)
    for patch in patches:
        name = relative(patch['file'])
        need(name in result, f'Compatibility patch target missing: {name}')
        old, new = patch['old'].encode(), patch['new'].encode()
        need(old and result[name].count(old) == patch['count'], f'Compatibility patch conflict: {name}')
        result[name] = result[name].replace(old, new)
    return result


def native_ids(manifest):
    return {u['skill'] for u in manifest['skills']} | {
        a['skill'] for a in manifest['audit'] if a['resolution'] == 'PRESERVED_UNCHANGED'}


def validate(bundle=BUNDLE):
    manifest = load_manifest(bundle)
    validate_agents(bundle, manifest)
    ids = native_ids(manifest)
    need(len(manifest['skills']) == len({u['skill'] for u in manifest['skills']}), 'Duplicate native skill ID')
    actual = {p.parent.name for p in (bundle / 'skills').glob('*/SKILL.md')}
    need(actual == ids, f'Native catalog differs from manifest: {actual ^ ids}')
    need(set(manifest['agents']) == ROLES, 'Role skill matrix must contain the six native agents')
    for role, selected in manifest['agents'].items():
        need(len(selected) == len(set(selected)) and set(selected) <= ids, f'Unknown/duplicate role skill: {role}')
        front, _, = read_agent(bundle, role)
        grants = {r['resource'] for r in front['permissions'] if r['action'] == 'skill' and r['effect'] == 'allow'}
        need(grants == set(selected), f'Agent skill permissions differ from manifest: {role}')
        for action in ('shell', 'subagent', 'execute', 'external_directory', 'edit'):
            expected = 'allow' if action == 'edit' or (role in ('poseidon', 'team-lead') and action in ('shell', 'external_directory')) else 'deny'
            need(permission(front['permissions'], action, '*') == expected, f'Unexpected native role capability: {role}/{action}')
        if role == 'poseidon':
            for child in ROLES - {'poseidon'}:
                need(permission(front['permissions'], 'subagent', child) == 'allow', f'Poseidon cannot delegate to {child}')
    for skill in ids:
        need(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', skill), f'Unstable native ID: {skill}')
        frontmatter(local(bundle, 'skills/' + skill + '/SKILL.md').read_bytes())
    for unit in units(manifest):
        apache = (unit.get('skill') == 'frontend-design'
                  and unit['upstreamRepository'] == 'https://github.com/anthropics/skills'
                  and unit['upstreamPath'] == 'skills/frontend-design'
                  and unit['licensePath'] == 'skills/frontend-design/LICENSE.txt'
                  and unit['license'] == 'Apache-2.0')
        need(unit['status'] == 'VERIFIED' and (unit['license'] == 'MIT' or apache),
             'Unverified import cannot be distributed')
        need(re.fullmatch(r'[a-f0-9]{40}', unit['upstreamCommit']), 'Upstream must be pinned to a full Git SHA')
        need(re.fullmatch(r'https://github.com/[\w.-]+/[\w.-]+', unit['upstreamRepository']), 'Non-canonical upstream repository')
        expected = {relative(f['path']): f for f in unit['files']}
        snapshot = inventory(local(bundle, unit['snapshot']))
        active = inventory(local(bundle, unit['destination']))
        need(set(snapshot) == set(expected), f'Unresolved snapshot additions/deletions: {unit["destination"]}')
        need(set(active) == set(expected), f'Unresolved local additions/deletions: {unit["destination"]}')
        if apache:
            need('LICENSE.txt' in snapshot and sha(snapshot['LICENSE.txt']) == '0d542e0c8804e39aa7f37eb00da5a762149dc682d7829451287e11b938e94594',
                 'Required approved Apache-2.0 license missing or changed')
            need('THIRD_PARTY_NOTICES.md' in snapshot, 'Required upstream notices missing')
        elif (unit.get('skill') == 'karpathy-guidelines'
              and unit['upstreamRepository'] == 'https://github.com/multica-ai/andrej-karpathy-skills'
              and unit['upstreamPath'] == 'skills/karpathy-guidelines'
              and unit['licensePath'] == 'skills/karpathy-guidelines/SKILL.md'):
            # Upstream declares MIT in SKILL.md and README, without a LICENSE file.
            need(sha(snapshot.get('SKILL.md', b'')) == '6e22cc54cb02a5e98ae42d06d9d7292db0c1b43894831b32879beb0166b2aea7'
                 and frontmatter(snapshot['SKILL.md']).get('license') == 'MIT',
                 'Karpathy guidelines source/license changed; review required')
        else:
            need('LICENSE' in snapshot and b'Permission is hereby granted' in snapshot['LICENSE'], 'Required MIT notice missing')
        for name, record in expected.items():
            need(sha(snapshot[name]) == record['sha256'], f'Upstream snapshot integrity mismatch: {unit["destination"]}/{name}')
            need(sha(active[name]) == record['installedSha256'], f'Unresolved local modification: {unit["destination"]}/{name}')
        for name in active:
            if name.endswith(('.py', '.sh', '.js', '.ts')) or '/scripts/' in '/' + name:
                need(not (local(bundle, unit['destination'] + '/' + name).stat().st_mode & 0o111),
                     'Imported script unexpectedly executable: ' + name)
        need(patched(snapshot, patches_for(unit, bundle)) == active, f'Installed content differs from snapshot plus compatibility patch: {unit["destination"]}')
    need(len(manifest['audit']) == len({a['skill'] for a in manifest['audit']}), 'Duplicate audit input')
    for audit in manifest['audit']:
        old = local(bundle, audit['preservedInput']).read_bytes()
        need(sha(old) == audit['inputSha256'], f'Audit input modified: {audit["skill"]}')
        if audit['resolution'] == 'PRESERVED_UNCHANGED':
            need(audit['status'] == 'SOURCE_UNVERIFIED' and old == local(bundle, audit['originalLocalPath']).read_bytes(),
                 f'Unverified skill changed: {audit["skill"]}')
    check_references(bundle, manifest)
    return {'nativeSkills': len(ids), 'verifiedImports': len(manifest['skills']),
            'unverifiedPreserved': sum(a['status'] == 'SOURCE_UNVERIFIED' for a in manifest['audit']),
            'importedFiles': sum(len(u['files']) for u in units(manifest))}


def validate_agents(bundle, manifest):
    """Static contract; live plugin gates additionally enforce task-specific restrictions."""
    need({p.stem for p in (bundle / 'agents').glob('*.md')} == ROLES, 'Unexpected agent catalog')
    config = json.loads((bundle / 'opencode.json').read_text())
    limits = json.loads((bundle / 'runtime/agent-limits.json').read_text())['roles']
    need(config.get('default_agent') == 'poseidon', 'Poseidon must remain default')
    need(all(config.get('agents', {}).get(r, {}).get('disabled') is True
             for r in ('build', 'plan', 'general', 'explore')), 'Built-in agents must remain disabled')
    protected = ('.opencode/opencode.json', '.opencode/agents/poseidon.md',
                 '.opencode/agents/team-lead.md', '.opencode/plugins/x.js', '.opencode/runtime/workspace.py',
                 '.opencode/skills/SOURCES.json', '.opencode/skill-sources/x',
                 'opencode.json', 'opencode.jsonc', '/tmp/project/.opencode/agents/coder.md',
                 '/home/user/.config/opencode/agents/poseidon.md')
    policies = config.get('policies', [])
    for path in protected:
        need(permission(policies, 'tool.use', 'edit:' + path) == 'deny', 'Missing hard-deny control-plane policy: ' + path)
    for role in ROLES:
        front, _ = read_agent(bundle, role)
        expected_model = ('openrouter/thinkingmachines/inkling:free' if role == 'researcher' else
                          'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free' if role == 'reviewer' else 'openai/gpt-6-sol')
        need(front.get('model') == expected_model, 'Unexpected model: ' + role)
        need(front.get('mode') == ('primary' if role == 'poseidon' else 'subagent'), 'Unexpected authority: ' + role)
        need(front.get('steps') == limits[role]['steps'], 'Agent steps differ from runtime limits: ' + role)
        rules = front['permissions']
        need(rules[0] == {'action': '*', 'resource': '*', 'effect': 'deny'}, 'Missing default deny: ' + role)
        allowed = {(a, '*') for a in ('read', 'glob', 'project_search', 'agent_contracts', 'system_access', 'edit')}
        if role in ('team-lead', 'poseidon'):
            allowed.add(('question', '*'))
        if role in ('poseidon', 'team-lead'):
            allowed.update((a, '*') for a in ('shell', 'external_directory'))
        if role == 'poseidon':
            allowed.update(('subagent', child) for child in ROLES - {role})
        else:
            need(rules[-1] == {'action': 'subagent', 'resource': '*', 'effect': 'deny'}, 'Missing final worker delegation deny: ' + role)
        allowed.update(('poseidon_workspace', a) for a in ('settings', 'status'))
        if role in ('poseidon', 'team-lead'):
            allowed.update(('poseidon_workspace', a) for a in ('configure', 'test', 'end_sandbox'))
        if role == 'researcher':
            allowed.update((a, '*') for a in ('webfetch', 'websearch', 'opencode_list_mcp_resources', 'opencode_read_mcp_resource'))
            need(manifest['agents'][role] == ['karpathy-guidelines'], 'Researcher skill scope changed')
        for skill in manifest['agents'][role]:
            allowed.add(('skill', skill))
            allowed.update((a, '~/.config/opencode/skills/' + skill + '/*') for a in ('read', 'external_directory'))
        grants = {(r['action'], r['resource']) for r in rules if r['effect'] != 'deny'}
        need(grants == allowed, 'Unauthorized or missing capability: ' + role)
        for path in protected:
            need(permission(rules, 'edit', path) == 'deny', 'Unprotected native edit: ' + role + '/' + path)
        need(permission(rules, 'external_directory', '/home/user/private') == ('allow' if role in ('poseidon', 'team-lead') else 'deny'), 'Unexpected external-directory capability')


def read_agent(bundle, role):
    _, front, body = (bundle / 'agents' / (role + '.md')).read_text().split('---', 2)
    return json.loads(front), body


def permission(rules, action, resource):
    def matches(pattern, value):
        return re.fullmatch(''.join('.*' if c == '*' else '.' if c == '?' else re.escape(c) for c in pattern), value, flags=re.S) is not None
    effect = 'ask'
    for rule in rules:
        if matches(rule['action'], action) and matches(rule['resource'], resource):
            effect = rule['effect']
    return effect


def check_references(bundle, manifest):
    """Verify shipped support links; explicit external/project links stay documented."""
    for unit in manifest['skills']:
        root = local(bundle, unit['destination'])
        for record in unit['files']:
            if not record['path'].endswith('.md'):
                continue
            path = root / record['path']
            text = path.read_text(encoding='utf-8')
            for target in re.findall(r'\[[^\]]+\]\(([^)\s]+)\)', text):
                if re.match(r'^[a-z]+://|^#|^mailto:', target):
                    continue
                target = target.split('#')[0]
                if target.startswith('.opencode/'):
                    need((bundle.parent / target).is_file(), f'Missing OpenCode resource: {target}')
                elif (path.parent / target).is_file():
                    continue
                else:
                    exceptions = manifest.get('externalReferences', {}).get(unit['skill'], [])
                    need(target in exceptions, f'Missing or undocumented relative link: {unit["skill"]}/{record["path"]} -> {target}')
            for target in re.findall(r'\.opencode/skill-resources/[A-Za-z0-9_./-]+', text):
                need((bundle / target.removeprefix('.opencode/')).exists(), f'Missing bundled plugin resource: {target}')


def installation_files(bundle=BUNDLE):
    validate(bundle)
    names = ['opencode.json']
    for directory in ('agents', 'skills', 'runtime', 'plugins', 'skill-sources', 'skill-resources'):
        for path in (bundle / directory).rglob('*'):
            name = path.relative_to(bundle).as_posix()
            if '__pycache__' in path.parts or path.suffix == '.pyc' or '/staged/' in name:
                continue
            need(not path.is_symlink(), f'Installer source is a symlink: {name}')
            if path.is_file():
                names.append(relative(name))
    return sorted(set(names))


def compare_install(bundle, destination):
    """Read-only inventory comparison; never merge or overwrite customized files."""
    names = installation_files(bundle)
    destination = destination.absolute()
    need(not destination.is_symlink(), 'Installation directory is a symlink; review its real location first')
    destination = destination.parent.resolve() / destination.name
    rows = []
    for name in names:
        parts = PurePosixPath(name).parts
        path = destination / name
        if any(destination.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts) + 1)):
            status = 'SYMLINK_REVIEW'
        elif not path.exists():
            status = 'MISSING'
        elif not path.is_file():
            status = 'TYPE_CONFLICT'
        else:
            status = 'IDENTICAL' if path.read_bytes() == (bundle / name).read_bytes() else 'DIFFERENT'
        rows.append({'path': name, 'status': status})
    jsonc = destination / 'opencode.jsonc'
    return {'destination': str(destination), 'files': rows,
            'existingJsonc': jsonc.exists() or jsonc.is_symlink(),
            'writes': 0, 'warning': 'Preserved files are not merged. Review differences as a bundle, then validate the chosen installation.'}


def git_fetch(repository, ref):
    """Bare public HTTPS inspection only. No checkout, hooks, filters or code execution."""
    need(re.fullmatch(r'https://github.com/[\w.-]+/[\w.-]+', repository), 'Only canonical public GitHub sources are supported')
    need(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', ref) and '..' not in ref and '//' not in ref, 'Unsafe upstream ref')
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_ALLOW_PROTOCOL='https', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    with tempfile.TemporaryDirectory(prefix='skill-upstream-') as tmp:
        def git(*args):
            p = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-C', tmp, *args],
                               env=env, capture_output=True, timeout=120)
            need(p.returncode == 0, 'Read-only Git inspection failed: ' + p.stderr.decode(errors='replace')[-2000:])
            return p.stdout
        git('init', '--bare', '-q')
        git('fetch', '--no-tags', '--depth=1', repository, ref)
        commit = git('rev-parse', 'FETCH_HEAD').decode().strip()
        tree = {}
        for item in git('ls-tree', '-rz', 'FETCH_HEAD').split(b'\0'):
            if not item:
                continue
            meta, name = item.split(b'\t', 1)
            mode, kind, oid = meta.decode().split()
            path = relative(name.decode())
            tree[path] = (mode, kind, oid)
        # Lazy blob access: only relevant selected files are retrieved.
        cache = {}
        def get(path):
            need(path in tree and tree[path][0] in ('100644', '100755') and tree[path][1] == 'blob', f'Unsupported upstream file: {path}')
            if path not in cache:
                size = int(git('cat-file', '-s', tree[path][2]))
                need(size <= 5_000_000, 'Oversized upstream file')
                cache[path] = git('cat-file', 'blob', tree[path][2])
            return cache[path]
        yield commit, tree, get


def notice_file(path):
    return re.match(r'(?i)^(license|copying|notice|third[_-]party[_-]notices?)(\.|$)', PurePosixPath(path).name) is not None


def select_files(unit, paths):
    selectors = unit['sourceSelectors']
    selected = set()
    for selector in selectors:
        need(selector in paths or any(p.startswith(selector + '/') for p in paths), f'Upstream source path removed: {selector}')
        selected.update(p for p in paths if p == selector or p.startswith(selector + '/'))
    # Newly introduced root notices/licenses must be reviewed as well.
    selected.update(p for p in paths if '/' not in p and notice_file(p))
    root = unit['upstreamPath']
    result = {}
    for path in selected:
        if path == unit['licensePath'] and unit['license'] != 'Apache-2.0' and notice_file(path):
            name = 'LICENSE'
        elif root == '.':
            name = path
        elif root == 'SKILL.md':
            name = path
        elif path.startswith(root + '/'):
            name = path[len(root)+1:]
        else:
            name = path
        relative(name)
        need(name not in result, 'Upstream file path collision')
        result[name] = path
    return result


def plan_update(bundle, skill, ref, fetcher=git_fetch):
    manifest = load_manifest(bundle)
    validate(bundle)
    source = next((u for u in manifest['skills'] if u['skill'] == skill), None)
    need(source is not None, 'Only verified imports can synchronize; unverified skills stay preserved')
    repository = source['upstreamRepository']
    # Update all packages from one repository together, including shared SEO resources.
    selected = [u for u in units(manifest) if u['upstreamRepository'] == repository]
    report = {'schemaVersion': 1, 'manifestSha256': sha((bundle / MANIFEST).read_bytes()),
              'repository': repository, 'requestedRef': ref, 'units': [], 'blockedReasons': [], 'diff': ''}
    for commit, tree, get in fetcher(repository, ref):
        for unit in selected:
            label = unit.get('skill', unit.get('id'))
            new = select_files(unit, tree)
            snapshots = {name: get(path) for name, path in new.items()}
            need(sum(map(len, snapshots.values())) < 50_000_000, 'Oversized upstream package')
            previous = inventory(local(bundle, unit['snapshot']))
            def licenses(values):
                return {p: sha(v) for p, v in values.items() if notice_file(p)}
            if licenses(previous) != licenses(snapshots):
                report['blockedReasons'].append('LICENSE_CHANGED: ' + label + '; review redistribution rights before updating the manifest')
            try:
                active = patched(snapshots, patches_for(unit, bundle))
            except SkillError as e:
                report['blockedReasons'].append(str(e))
                active = snapshots
            before = inventory(local(bundle, unit['destination']))
            for name in sorted(before.keys() | active.keys()):
                if before.get(name) != active.get(name):
                    report['diff'] += ''.join(difflib.unified_diff(
                        before.get(name, b'').decode(errors='replace').splitlines(True),
                        active.get(name, b'').decode(errors='replace').splitlines(True),
                        fromfile=label + '/' + name + ' (installed)', tofile=label + '/' + name + ' (proposed)'))
            report['units'].append({'destination': unit['destination'], 'commitBefore': unit['upstreamCommit'],
                 'commitAfter': commit, 'upstreamPaths': new,
                 'snapshotFiles': {p: base64.b64encode(v).decode() for p, v in snapshots.items()},
                 'upstreamGitModes': {p: tree[path][0] for p, path in new.items()},
                 'changedScripts': [p for p, v in active.items() if before.get(p) != v and (p.endswith(('.py', '.sh', '.js', '.ts')) or '/scripts/' in '/' + p)]})
    need(report['units'], 'No upstream inspection result')
    return report


def apply_update(bundle, report_bytes, reviewed_hash):
    need(sha(report_bytes) == reviewed_hash, 'Review fingerprint does not match this update report')
    report = json.loads(report_bytes)
    need(report.get('schemaVersion') == 1 and not report.get('blockedReasons'), 'Update blocked by licensing or compatibility conflicts')
    need(sha((bundle / MANIFEST).read_bytes()) == report['manifestSha256'], 'Manifest changed after update planning')
    validate(bundle)  # Includes all local additions, deletions, bytes, snapshots and patch hashes.
    manifest = load_manifest(bundle)
    updated = json.loads(json.dumps(manifest))
    changes = {}
    destinations = set()
    for proposal in report['units']:
        need(proposal['destination'] not in destinations, 'Duplicate proposal destination')
        destinations.add(proposal['destination'])
        unit = next((u for u in units(updated) if u['destination'] == proposal['destination']), None)
        need(unit and unit['upstreamRepository'] == report['repository'] and unit['upstreamCommit'] == proposal['commitBefore'], 'Update source no longer matches')
        need(re.fullmatch(r'[a-f0-9]{40}', proposal['commitAfter']), 'Update commit must be pinned')
        snapshots = {relative(p): base64.b64decode(v, validate=True) for p, v in proposal['snapshotFiles'].items()}
        need(set(snapshots) == set(proposal['upstreamPaths']), 'Update file provenance missing')
        old_snapshot = inventory(local(bundle, unit['snapshot']))
        license_names = {p for p in old_snapshot.keys() | snapshots.keys()
                         if notice_file(p)}
        need(all(old_snapshot.get(p) == snapshots.get(p) for p in license_names),
             'License changed; redistribution rights must be reviewed before synchronization')
        active = patched(snapshots, patches_for(unit, bundle))
        old_paths = {f['path'] for f in unit['files']}
        unit['files'] = [{'path': p, 'upstreamPath': relative(proposal['upstreamPaths'][p]),
                          'sha256': sha(v), 'installedSha256': sha(active[p]),
                          'upstreamGitMode': proposal['upstreamGitModes'][p], 'installedMode': '0644'} for p, v in sorted(snapshots.items())]
        for f in unit['files']:
            need(f['upstreamGitMode'] in ('100644', '100755'), 'Unsupported upstream file mode')
        unit['compatibilityChanges'] = [c for c in unit['compatibilityChanges'] if not c['reason'].startswith('Installed with mode 0644')]
        unit['compatibilityChanges'] += [{'file': f['path'], 'reason': 'Installed with mode 0644 so imported upstream programs are inert; source bytes are unchanged and upstream Git mode is recorded.'}
                                         for f in unit['files'] if f['upstreamGitMode'] == '100755']
        unit['upstreamCommit'] = proposal['commitAfter']
        unit['lastSynchronized'] = date.today().isoformat()
        for prefix, values in ((unit['snapshot'], snapshots), (unit['destination'], active)):
            for path in old_paths | values.keys():
                changes[prefix + '/' + relative(path)] = values.get(path)
    expected = {u['destination'] for u in units(manifest) if u['upstreamRepository'] == report['repository']}
    need(destinations == expected, 'Update must include the entire upstream repository group')
    changes[MANIFEST] = encoded(updated)
    # Validate the complete proposed bundle before touching installed files.
    with tempfile.TemporaryDirectory(prefix='skill-update-validation-') as tmp:
        staged = Path(tmp) / '.opencode'
        shutil.copytree(bundle, staged, ignore=shutil.ignore_patterns('__pycache__', 'staged'))
        for name, data in changes.items():
            p = local(staged, name)
            if data is None:
                p.unlink()
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
        validate(staged)
    need(sha((bundle / MANIFEST).read_bytes()) == report['manifestSha256'], 'Manifest changed during staging')
    validate(bundle)
    backup = {name: local(bundle, name).read_bytes() if local(bundle, name).is_file() else None for name in changes}
    lock = bundle / '.skill-update.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    applied = []
    try:
        for name, data in changes.items():
            path = local(bundle, name)
            need((path.read_bytes() if path.is_file() else None) == backup[name],
                 'Local file changed during update: ' + name)
            if data is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(path.name + '.skill-update-tmp')
                with tmp.open('xb') as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                tmp.chmod(0o644)  # Imported scripts remain non-executable.
                os.replace(tmp, path)
            applied.append(name)
    except BaseException:
        for name in reversed(applied):
            data = backup[name]
            path = local(bundle, name)
            if (path.read_bytes() if path.is_file() else None) != changes[name]:
                continue  # Preserve a concurrent user's edit rather than overwriting it during rollback.
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)
        raise
    finally:
        lock.unlink()
    return {'updatedRepository': report['repository'], 'updatedUnits': len(report['units']), 'executedScripts': []}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=BUNDLE)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('validate')
    sub.add_parser('install-files')
    p = sub.add_parser('compare-install')
    p.add_argument('destination', type=Path, help='Existing .opencode or global opencode directory; read-only')
    p = sub.add_parser('check')
    p.add_argument('skill')
    p.add_argument('--ref', default='HEAD')
    p.add_argument('--report', type=Path, required=True)
    p = sub.add_parser('apply')
    p.add_argument('report', type=Path)
    p.add_argument('--reviewed', required=True, help='SHA256 of the exact diff report you reviewed')
    args = parser.parse_args(argv)
    try:
        if args.command == 'validate':
            print(json.dumps(validate(args.bundle), indent=2))
        elif args.command == 'install-files':
            print('\n'.join(installation_files(args.bundle)))
        elif args.command == 'compare-install':
            print(json.dumps(compare_install(args.bundle, args.destination), indent=2))
        elif args.command == 'check':
            report = plan_update(args.bundle, args.skill, args.ref)
            data = encoded(report)
            # Never overwrite an existing report or write a report over managed content.
            need(not args.report.resolve().is_relative_to(args.bundle.resolve()), 'Place update reports outside the installed bundle')
            with args.report.open('xb') as f:
                f.write(data)
            print(report['diff'] or 'No imported file content changed.')
            print(json.dumps({'report': str(args.report), 'reviewFingerprint': sha(data), 'blockedReasons': report['blockedReasons']}, indent=2))
        else:
            print(json.dumps(apply_update(args.bundle, args.report.read_bytes(), args.reviewed), indent=2))
        return 0
    except (SkillError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as e:
        print('Skill operation stopped: ' + str(e), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
