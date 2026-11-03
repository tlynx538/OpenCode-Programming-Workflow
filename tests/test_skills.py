import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SUPPORT = Path(__file__).resolve().parents[1] / '.opencode/runtime'
sys.path.insert(0, str(SUPPORT))
import skillctl as s


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bundle = Path(self.tmp.name) / '.opencode'
        shutil.copytree(s.BUNDLE, self.bundle, ignore=shutil.ignore_patterns('__pycache__'))
        self.manifest = s.load_manifest(self.bundle)

    def tearDown(self):
        self.tmp.cleanup()

    def fetcher(self, mutate=None):
        def fetch(repository, ref):
            source = {}
            for u in s.units(self.manifest):
                if u['upstreamRepository'] == repository:
                    for f in u['files']:
                        source[f['upstreamPath']] = (self.bundle / u['snapshot'] / f['path']).read_bytes()
            if mutate:
                mutate(source)
            yield 'a' * 40, dict.fromkeys(source, ('100644', 'blob', 'unused')), source.__getitem__
        return fetch

    def test_complete_catalog_and_all_seventeen_audit_inputs(self):
        result = s.validate(self.bundle)
        self.assertEqual(result['verifiedImports'], 21)
        self.assertEqual(result['unverifiedPreserved'], 6)
        self.assertEqual(result['nativeSkills'], 27)
        self.assertEqual(len(self.manifest['audit']), 17)
        for u in self.manifest['skills']:
            self.assertEqual(s.inventory(self.bundle / u['destination']),
                             s.patched(s.inventory(self.bundle / u['snapshot']), s.patches_for(u, self.bundle)))

    def test_methodologies_are_not_generic_rewrites(self):
        tdd = (self.bundle / 'skills/tdd/SKILL.md').read_text()
        self.assertIn('**One slice at a time.** One seam, one test, one minimal implementation per cycle.', tdd)
        self.assertIn('**Refactoring is not part of the loop.**', tdd)
        debugging = (self.bundle / 'skills/systematic-debugging/SKILL.md').read_text()
        self.assertIn('NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST', debugging)
        self.assertIn('### Phase 1: Root Cause Investigation', debugging)
        self.assertNotIn('## Governed execution', debugging)
        self.assertTrue((self.bundle / 'skills/systematic-debugging/root-cause-tracing.md').is_file())

    def test_karpathy_guidelines_available_to_every_agent_and_global_install(self):
        for role in s.ROLES:
            front, body = s.read_agent(self.bundle, role)
            self.assertIn('karpathy-guidelines', self.manifest['agents'][role])
            for action, resource in [('skill', 'karpathy-guidelines'),
                                     ('read', '~/.config/opencode/skills/karpathy-guidelines/SKILL.md'),
                                     ('external_directory', '~/.config/opencode/skills/karpathy-guidelines/SKILL.md')]:
                with self.subTest(role=role, action=action):
                    self.assertEqual(s.permission(front['permissions'], action, resource), 'allow')
        files = s.installation_files(self.bundle)
        self.assertIn('skills/karpathy-guidelines/SKILL.md', files)
        self.assertIn('skill-sources/upstream/karpathy-guidelines/SKILL.md', files)

    def test_karpathy_source_license_declaration_cannot_be_silently_changed(self):
        def mutate(source):
            source['skills/karpathy-guidelines/SKILL.md'] = source['skills/karpathy-guidelines/SKILL.md'].replace(b'license: MIT', b'license: UNKNOWN')
        report = s.plan_update(self.bundle, 'karpathy-guidelines', 'main', self.fetcher(mutate))
        data = s.encoded(report)
        with self.assertRaises(s.SkillError):
            s.apply_update(self.bundle, data, s.sha(data))

    def test_vision_interview_skills_and_dependencies_have_scoped_access(self):
        for role in ('poseidon',):
            front, _ = s.read_agent(self.bundle, role)
            for skill in ('grilling', 'grill-with-docs', 'domain-modeling'):
                self.assertIn(skill, self.manifest['agents'][role])
                for action, resource in [('skill', skill),
                                         ('read', '~/.config/opencode/skills/' + skill + '/SKILL.md'),
                                         ('external_directory', '~/.config/opencode/skills/' + skill + '/SKILL.md')]:
                    with self.subTest(role=role, skill=skill, action=action):
                        self.assertEqual(s.permission(front['permissions'], action, resource), 'allow')
        for role in s.ROLES:
            front, _ = s.read_agent(self.bundle, role)
            self.assertEqual(s.permission(front['permissions'], 'skill', 'gtd'),
                             'allow' if role == 'poseidon' else 'deny')
        researcher, _ = s.read_agent(self.bundle, 'researcher')
        self.assertEqual(s.permission(researcher['permissions'], 'read', '~/.config/opencode/opencode.json'), 'deny')
        self.assertEqual(s.permission(researcher['permissions'], 'external_directory', '~/.config/opencode/skills/gtd/SKILL.md'), 'deny')

    def test_gtd_root_import_preserves_references_license_and_update_paths(self):
        unit = next(u for u in self.manifest['skills'] if u['skill'] == 'gtd')
        self.assertEqual(unit['upstreamCommit'], 'e192366199ba543505ff8d5caf88d31c40a4ae90')
        self.assertEqual(len(list((self.bundle / unit['destination'] / 'references').glob('*.md'))), 9)
        license_text = (self.bundle / unit['destination'] / 'LICENSE').read_text()
        self.assertIn('Copyright (c) 2026 Zerui Wang', license_text)
        self.assertIn('this MIT grant does not extend to those', license_text)
        files = s.installation_files(self.bundle)
        for prefix in ('skills/gtd', 'skill-sources/upstream/gtd'):
            for path in ('LICENSE', 'SKILL.md', 'references/04-natural-planning.md'):
                self.assertIn(prefix + '/' + path, files)
        report = s.plan_update(self.bundle, 'gtd', 'main', self.fetcher())
        self.assertEqual(report['diff'], '')
        self.assertEqual(report['blockedReasons'], [])
        self.assertEqual(report['units'][0]['upstreamPaths']['references/04-natural-planning.md'],
                         'references/04-natural-planning.md')
        data = s.encoded(report)
        s.apply_update(self.bundle, data, s.sha(data))
        s.validate(self.bundle)

    def test_missing_gtd_reference_fails_validation(self):
        (self.bundle / 'skills/gtd/references/04-natural-planning.md').unlink()
        with self.assertRaises(s.SkillError):
            s.validate(self.bundle)

    def test_unverified_inputs_remain_byte_identical(self):
        for a in self.manifest['audit']:
            if a['status'] == 'SOURCE_UNVERIFIED':
                self.assertEqual((self.bundle / a['preservedInput']).read_bytes(),
                                 (self.bundle / a['originalLocalPath']).read_bytes())
                self.assertEqual(a['license'], 'UNVERIFIED')

    def test_source_tampering_and_local_changes_fail_closed(self):
        for relative in ('skills/tdd/SKILL.md', 'skill-sources/upstream/tdd/SKILL.md',
                         'skill-sources/patches/seo-content.json'):
            p = self.bundle / relative
            original = p.read_bytes()
            p.write_bytes(original + b'\nlocal edit\n')
            with self.subTest(path=relative), self.assertRaises(s.SkillError):
                s.validate(self.bundle)
            p.write_bytes(original)

    def test_missing_resource_license_or_support_file_fails(self):
        for relative in ('skills/tdd/LICENSE', 'skills/tdd/tests.md',
                         'skill-resources/claude-seo/skills/seo/references/eeat-framework.md'):
            p = self.bundle / relative
            original = p.read_bytes()
            p.unlink()
            with self.subTest(path=relative), self.assertRaises(s.SkillError):
                s.validate(self.bundle)
            p.write_bytes(original)

    def test_unknown_local_support_file_is_not_silently_overwritten(self):
        p = self.bundle / 'skills/tdd/local-notes.md'
        p.write_text('unresolved local notes')
        with self.assertRaises(s.SkillError):
            s.plan_update(self.bundle, 'tdd', 'main', self.fetcher())
        self.assertEqual(p.read_text(), 'unresolved local notes')

    def test_native_ids_frontmatter_and_manual_discovery_flags(self):
        for u in self.manifest['skills']:
            f = s.frontmatter((self.bundle / u['destination'] / 'SKILL.md').read_bytes())
            self.assertTrue(f['description'])
        self.assertEqual(s.frontmatter((self.bundle / 'skills/to-spec/SKILL.md').read_bytes())['disable-model-invocation'], 'true')
        for bad in (b'no frontmatter', b'---\nname: x\n---\nbody', b'---\nname: x\nname: y\ndescription: z\n---'):
            with self.assertRaises(s.SkillError):
                s.frontmatter(bad)

    def test_roles_only_have_appropriate_native_skill_permissions(self):
        for role in s.ROLES:
            front, body = s.read_agent(self.bundle, role)
            for skill in s.native_ids(self.manifest):
                self.assertEqual(s.permission(front['permissions'], 'skill', skill),
                                 'allow' if skill in self.manifest['agents'][role] else 'deny')
            for action in ('edit', 'shell', 'subagent', 'execute', 'unknown_tool', 'random_mcp_tool'):
                expected = 'allow' if action == 'edit' or (role in ('poseidon', 'team-lead') and action == 'shell') else 'deny'
                self.assertEqual(s.permission(front['permissions'], action, '*'), expected)
            # Definitions explain integration, not embedded author methodologies.
            self.assertNotIn('NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST', body)
        self.assertNotIn('grilling', self.manifest['agents']['reviewer'])
        self.assertNotIn('tdd', self.manifest['agents']['team-lead'])
        self.assertIn('code-review', self.manifest['agents']['reviewer'])

    def test_update_is_diff_first_and_preserves_compatibility_patch(self):
        before = (self.bundle / 'skills/seo-content/SKILL.md').read_bytes()
        patch_path = self.bundle / 'skill-sources/patches/seo-content.json'
        patch_before = patch_path.read_bytes()
        def mutate(source):
            source['skills/seo-content/SKILL.md'] += b'\nUpstream release note.\n'
        report = s.plan_update(self.bundle, 'seo-content', 'main', self.fetcher(mutate))
        self.assertIn('+Upstream release note.', report['diff'])
        self.assertEqual((self.bundle / 'skills/seo-content/SKILL.md').read_bytes(), before)
        data = s.encoded(report)
        with self.assertRaises(s.SkillError):
            s.apply_update(self.bundle, data, 'unreviewed')
        result = s.apply_update(self.bundle, data, s.sha(data))
        self.assertEqual(result['updatedUnits'], 3)  # Both skills plus shared resources stay pinned together.
        self.assertEqual(result['executedScripts'], [])
        self.assertIn(b'Upstream release note.', (self.bundle / 'skills/seo-content/SKILL.md').read_bytes())
        self.assertEqual(patch_path.read_bytes(), patch_before)
        self.assertIn(b'.opencode/skill-resources/claude-seo', (self.bundle / 'skills/seo-content/SKILL.md').read_bytes())
        self.assertNotIn(b'${CLAUDE_PLUGIN_ROOT}', (self.bundle / 'skills/seo-content/SKILL.md').read_bytes())
        s.validate(self.bundle)

    def test_changed_license_blocks_update_and_apply_rechecks_it(self):
        def mutate(source):
            source['LICENSE'] += b'\nChanged redistribution terms.\n'
        report = s.plan_update(self.bundle, 'tdd', 'main', self.fetcher(mutate))
        self.assertTrue(any('LICENSE_CHANGED' in b for b in report['blockedReasons']))
        data = s.encoded(report)
        with self.assertRaises(s.SkillError):
            s.apply_update(self.bundle, data, s.sha(data))
        # Even a modified report cannot bypass the independent apply-time licensing check.
        report['blockedReasons'] = []
        data = s.encoded(report)
        with self.assertRaisesRegex(s.SkillError, 'License changed'):
            s.apply_update(self.bundle, data, s.sha(data))

    def test_patch_conflict_is_reported_without_modifying_source(self):
        before = (self.bundle / 'skills/seo-content/SKILL.md').read_bytes()
        def mutate(source):
            source['skills/seo-content/SKILL.md'] += b'\n${CLAUDE_PLUGIN_ROOT}/new-reference\n'
        report = s.plan_update(self.bundle, 'seo-content', 'main', self.fetcher(mutate))
        self.assertTrue(any('Compatibility patch conflict' in v for v in report['blockedReasons']))
        self.assertEqual((self.bundle / 'skills/seo-content/SKILL.md').read_bytes(), before)

    def test_local_modification_after_diff_blocks_apply(self):
        report = s.plan_update(self.bundle, 'tdd', 'main', self.fetcher())
        p = self.bundle / 'skills/tdd/tests.md'
        p.write_bytes(p.read_bytes() + b'local change')
        data = s.encoded(report)
        with self.assertRaises(s.SkillError):
            s.apply_update(self.bundle, data, s.sha(data))
        self.assertTrue(p.read_bytes().endswith(b'local change'))

    def test_changed_scripts_are_reported_and_never_executed(self):
        def mutate(source):
            source['scripts/content_humanize.py'] += b'\n# update inspection fixture\n'
        report = s.plan_update(self.bundle, 'seo-content', 'main', self.fetcher(mutate))
        self.assertTrue(any('scripts/content_humanize.py' in u['changedScripts'] for u in report['units']))
        with patch.object(s.subprocess, 'run', side_effect=AssertionError('No execution allowed')):
            data = s.encoded(report)
            s.apply_update(self.bundle, data, s.sha(data))
        self.assertFalse((self.bundle / 'skill-resources/claude-seo/scripts/content_humanize.py').stat().st_mode & 0o111)

    def test_source_snapshots_not_in_discovery_and_installer_is_recursive(self):
        self.assertNotIn('skill-sources', (self.bundle / 'opencode.json').read_text())
        files = s.installation_files(self.bundle)
        for name in ('skills/tdd/tests.md', 'skills/tdd/LICENSE', 'skills/SOURCES.json',
                     'skill-sources/upstream/tdd/SKILL.md', 'skill-sources/patches/seo-content.json',
                     'skill-resources/claude-seo/scripts/content_humanize.py', 'runtime/skillctl.py'):
            self.assertIn(name, files)
        self.assertFalse(any('__pycache__' in f for f in files))


if __name__ == '__main__':
    unittest.main()
