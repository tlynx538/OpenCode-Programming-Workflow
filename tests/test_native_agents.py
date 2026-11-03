import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.opencode/runtime'))
import skillctl


class NativeAgentTests(unittest.TestCase):
    def test_default_coordinator_and_all_models_use_native_md_definitions(self):
        config = json.loads((ROOT / '.opencode/opencode.json').read_text())
        self.assertEqual(config['default_agent'], 'poseidon')
        for role in skillctl.ROLES:
            front, _ = skillctl.read_agent(skillctl.BUNDLE, role)
            self.assertEqual(front['model'], 'openrouter/thinkingmachines/inkling:free' if role == 'researcher' else 'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free' if role == 'reviewer' else 'openai/gpt-6-sol')
            self.assertEqual(front['mode'], 'primary' if role == 'poseidon' else 'subagent')

    def test_poseidon_delegates_and_native_shell_is_denied(self):
        coordinator, _ = skillctl.read_agent(skillctl.BUNDLE, 'poseidon')
        for role in skillctl.ROLES - {'poseidon'}:
            self.assertEqual(skillctl.permission(coordinator['permissions'], 'subagent', role), 'allow')
        coder, _ = skillctl.read_agent(skillctl.BUNDLE, 'coder')
        self.assertEqual(skillctl.permission(coder['permissions'], 'edit', 'web/src/app.tsx'), 'allow')
        self.assertEqual(skillctl.permission(coder['permissions'], 'shell', 'git diff'), 'deny')
        self.assertEqual(skillctl.permission(coder['permissions'], 'edit', '.env'), 'deny')
        self.assertEqual(skillctl.permission(coder['permissions'], 'edit', '.opencode/agents/poseidon.md'), 'deny')
        self.assertEqual(skillctl.permission(coder['permissions'], 'subagent', 'poseidon'), 'deny')
        reviewer, _ = skillctl.read_agent(skillctl.BUNDLE, 'reviewer')
        self.assertEqual(skillctl.permission(reviewer['permissions'], 'shell', 'bash -lc pwd'), 'deny')
        self.assertEqual(skillctl.permission(reviewer['permissions'], 'edit', 'web/src/app.tsx'), 'allow')


if __name__ == '__main__':
    unittest.main()
