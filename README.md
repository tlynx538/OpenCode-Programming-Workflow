# OpenCode Programming Workflow

A six-agent workflow for turning a user's idea into working software: clarify the
intended outcome, challenge assumptions, plan the work, implement it, and review
actual evidence. Prompts emphasize completing the user's main workflow rather
than producing an attractive interface with missing behavior.

Built with this workflow: **[PocketCalc](https://github.com/tlynx538/calc)**, a native
macOS calculator, and **[EmberText](https://github.com/tlynx538/embertext)**, a graphical
desktop text editor. OpenCode agents created both from empty repositories. See
[the project stories](#projects-built-with-the-agents).

## What it does

- Clarifies consequential choices before implementation: audience, platform,
  primary workflows, state, outputs and external effects.
- Separates confirmed user decisions, observed facts, assumptions and proposals.
  Existing code or a familiar reference product does not define user intent.
- Gives Researcher an independent challenge of ambiguous product briefs so an
  early coordinator assumption does not propagate unchecked.
- Passes the original request and confirmed answers through planning, scoped
  implementation and independent review.
- Keeps question rounds small and relevant. Required questions default to ordinary
  numbered chat; agents wait for actual answers or explicit delegation before
  changing dependent behavior. Precise fixes skip unnecessary interviews.
- Provides bounded runtime tools, Docker test workspaces, skill provenance checks,
  and an offline benchmark for evaluating prompt changes against task outcomes.

The coordinator and research prompts also retain selected guidance from the local
CLI skill catalog, with fallbacks for unavailable optional skills. See the
[adaptation review](docs/LOCAL_SKILL_ADAPTATION.md) for role mappings and limits.

## Agents and responsibilities

| Agent | Responsibility | Configured model |
| --- | --- | --- |
| **Team Lead** | Execution, task decomposition, dependencies, assignments, acceptance checks and escalation | `openai/gpt-6-sol` |
| **Poseidon** | User intent, first-principles discovery, focused questioning, design briefs and fidelity checks | `openai/gpt-6-sol` |
| **Researcher** | Evidence gathering with remote read-only and scoped local writes; challenges assumptions and overlooked workflows; distinguishes facts from preferences | `openrouter/thinkingmachines/inkling:free` |
| **Maintainer** | Architecture, platform feasibility, compatibility and capability fit | `openai/gpt-6-sol` |
| **Coder** | Scoped implementation, working user journeys and regression checks | `openai/gpt-6-sol` |
| **Reviewer** | Independent correctness and requirement review; checks claims against source and actual test evidence | `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` |

The human remains the final authority. Research and agent consensus cannot answer
preference questions on the user's behalf. Provider access depends on your own
OpenCode connections and model availability.

### Repository bundle versus the tested installation

This repository's bundle starts with **Poseidon as the sole primary coordinator**.
Poseidon owns discovery and execution, and delegates to Team Lead for planning or
to the other specialists through explicit assignment/handoff contracts. Workers
cannot launch agents. Agents retain their scoped read, search, edit, skill and
configured sandbox test tools. Permitted native tools are exposed directly
without Code Mode. Host shell belongs to Poseidon/Team Lead; other agents use
the restricted system-access tool.

The installed configuration that built PocketCalc was the earlier **Poseidon-led
native workflow**, with Team Lead as a planning worker. Discovery v2 prompt updates
were installed into that configuration while preserving its models, permissions
and hierarchy. Its workers had native host tools; it did not use the repository's
assignment and evidence controls. PocketCalc is evidence for that tested workflow,
not proof that every newer runtime control in this bundle has been live-validated.
See [the discovery update](docs/usage-reviews/2026-11-01-discovery-v2.md) and
[calculator session review](docs/usage-reviews/2026-11-01-calculator-session-reflection.md).

## How the workflow works

1. **Discover intent.** Inspect available facts and reconstruct the main user
   journey before choosing a solution. For ambiguous products or broad audits,
   Poseidon asks one to three dependency-aware questions per round and carries
   actual answers forward. Missing responses and interrupted widgets are not consent.
2. **Challenge the interpretation.** The coordinator gives Researcher the original
   request, confirmed answers and proposed scope. Researcher surfaces unsupported
   assumptions, factual constraints and overlooked steps. Material preference
   questions return to the user; factual questions receive bounded investigation.
3. **Form a shared brief and plan.** Record confirmed outcomes, constraints, action
   semantics, acceptance checks and material unknowns. Team Lead maps requirements
   to owners and observable checks. Maintainer checks feasibility before a stack
   or architecture is committed to.
4. **Implement the core journey.** Coder builds the smallest useful end-to-end
   slice before optional polish. Necessary choices must be discoverable, and
   cancellation, failures and unintended side effects receive relevant checks.
5. **Review and deliver.** Reviewer assesses both patch correctness and coverage
   of the original request. Source inspection, unit checks, interactive evidence
   and user feedback remain distinct. Passing a build does not prove a usable UI.

In the current repository bundle, Poseidon proposes a versioned brief for design
work. Inspect the actual proposal and invoke the returned operator command:

```text
/confirm-brief ID VERSION HASH
```

The hash binds confirmation to what you saw. Agents cannot self-confirm or silently
replace accepted decisions. Reuse settled choices; precise tasks stay lightweight.
The earlier Poseidon-led installation uses conversational clarification rather
than this contract command. Do not mix installation profiles accidentally.

First-principles and Socratic **discovery methods are embedded in the prompts**.
They support direct answers and delivery; the tutor-only rule that refuses answers
was not adopted. Original upstream grilling skill files remain unchanged.

## Skills available to the agents

Skills load on demand and only where assigned. This is the bundled catalog, not a
claim that every skill runs on every project. Exact role grants, upstream revisions,
file hashes and licenses are in [SOURCES.json](.opencode/skills/SOURCES.json).

| Purpose | Native skill IDs |
| --- | --- |
| Clarification and domain discovery | `grilling`, `grill-with-docs`, `domain-modeling` |
| Reasoning and planning | `how`, `codebase-design`, `to-spec`, `to-tickets`, `writing-plans`, `milestone-coordination` |
| Implementation and diagnosis | `tdd`, `superpowers-test-driven-development`, `systematic-debugging`, `diagnosing-bugs`, `code-quality` |
| Review and verification | `code-review`, `verification-before-completion`, `verification` |
| User outcomes and next actions | `karpathy-guidelines`, `gtd` |
| Interface design | `frontend-design` |
| Writing and discoverability | `humanizer`, `human-writing`, `seo-content`, `seo-technical` |
| Commerce tasks | `ecommerce-brand-voice`, `ecommerce-copywriting`, `ecommerce-product-pages` |

Poseidon automatically loads `grilling` for new products, UI/UX work including repairs,
redesigns, broad audits and materially ambiguous behavior changes. No explicit
“grill” request is needed. Settled decisions are reused; precise fixes avoid
unnecessary interviews. “Grill me”, “grill-me” and “grill” also refer to `grilling`. `grill-with-docs` is used
when explicitly requested. GTD helps clarify outcomes and next actions; it does
not authorize messages, calendar events or unrelated product features.

The catalog contains 27 native skills: 21 verified imports and six preserved legacy
adaptations marked `SOURCE_UNVERIFIED` (`milestone-coordination`, `code-quality`,
`verification`, and the three commerce skills). Original licenses and notices are
retained. See [ATTRIBUTION.md](ATTRIBUTION.md) and
[skill provenance](docs/SKILL_PROVENANCE.md). Discovery method references:
[First Principles Thinking](https://github.com/awesome-skills/first-principles-skill)
and [Socrates](https://github.com/bevibing/socrates-skill); these were adapted
conceptually in prompts, not installed as unchanged additional skills.

## Projects built with the agents

### PocketCalc — native macOS calculator

**Repository: [tlynx538/calc](https://github.com/tlynx538/calc)**

OpenCode's agents created the calculator from an empty Git repository. The human
provided the idea and answered product questions; the agents produced the SwiftUI
application, arithmetic engine, executable checks, documentation and `.app`
packaging script. This later publishing pass added provenance documentation and
GitHub publication; it did not write the calculator implementation.

The questions changed the outcome: the user chose a native macOS desktop app over
a proposed web app, mathematical precedence, a dark body, raised keys and an
LCD-style display. The app includes keyboard controls, basic arithmetic, percent,
square root, sign changes, memory, entry correction and error recovery.

Recorded evidence includes passing engine assertions, a successful build, final
`.app` packaging and launch smoke checks. Poseidon also caught a clear-entry bug
and ensured the corrected source was repackaged. The user reported a successful
result. Visual inspection and an interactive keyboard walkthrough were not
performed by the agents; those are distinct from a launch check. See the
[session assessment](docs/usage-reviews/2026-11-01-calculator-session-reflection.md).

### EmberText — lightweight desktop text editor

**Repository: [tlynx538/embertext](https://github.com/tlynx538/embertext)**

The Poseidon-led OpenCode agents built this graphical editor from an empty
repository after clarifying desktop delivery, arbitrary filename extensions and
the user's lightweight preference. They produced a standard-library Python/Tkinter
application with tabs, local Open/Save/Save As, dirty-change prompts, find/replace,
undo/redo, line numbers, keyboard shortcuts and basic syntax highlighting.

The final agent run recorded 20 passing tests, including real Tk widget workflows
with mocked dialog choices for saves, cancellation, failed file operations and
editing. The user reported a positive result. Visual inspection and Windows/Linux
validation remain unavailable. A later review reproduced a Find Next bug when the
caret is at the document start; the published README documents it. See the
[EmberText session assessment](docs/usage-reviews/2026-11-01-embertext-session-reflection.md).

PocketCalc and EmberText are positive human-reviewed examples with documented
limits, not controlled benchmark scores. The older browser-editor failure remains
historical evidence that informed these prompts.

## Install

Requirements: OpenCode v2 (validated against v2.2.5), Git, Python 3.10+, Node for
local runtime checks, and Docker for configured sandbox tests. Use your existing
provider logins; no credentials are bundled.

```sh
./install.sh --project /path/to/project --dry-run
./install.sh --project /path/to/project
# Or install missing files globally:
./install.sh --global
```

Windows: `./install.ps1 -Project 'C:\Projects\MyApp'` or `-Global`; use `-DryRun`
to preview. Native PowerShell execution has not been verified on the macOS host.

Installers preserve existing files. An existing installation needs a deliberate
[merge/migration](docs/MIGRATION.md), validation and a fresh chat. Running the
installer or restarting alone does not replace an old profile. A fresh installation
of this bundle starts with Team Lead; the author's existing global installation
still uses the tested Poseidon-led profile described above.

The workspace plugin uses an installation-specific ID to avoid project/global
collisions. When a legacy global workspace tool is already registered, local guards
reuse it rather than starting duplicate sandbox hooks and monitors. Verify actual
agent and plugin discovery when comparing installations.

## Tools, testing and resource controls

The repository grants Poseidon and Team Lead host shell for authorized
administration. Researcher, Maintainer, Coder and Reviewer have remote read-only
operations and scoped local development writes through `system_access` and an
isolated command runner. See [system access](docs/SYSTEM_ACCESS.md) for setup,
connection profiles and the enforcement boundaries. Trusted server plugins and
operator actions remain privileged.

The operator configures Docker images and commands. Agents run configured tests
through `poseidon_workspace`; missing setup is an explicit verification limitation.
Sandbox snapshots exclude protected files and run without host mounts or runtime
network. Settings/logs remain under the Git common directory's `.git/bdfl/` storage.
See [settings examples](.opencode/runtime/settings.example.json).

Default resource admission is one worker, one heavy tool and one delegation level.
[agent-limits.json](.opencode/runtime/agent-limits.json) adds per-role step, call,
time and output budgets. Research defaults to three searches, four retrievals,
24 calls, 16 steps, 300 seconds and a suggested 600-word report. Reports can use
minimal submit objects or ordinary final prose; routing is automatic and unreviewed
reports stay PARTIAL. Public help/evidence actions avoid reading protected runtime files. A final submission
slot is reserved. Limits do not make incomplete evidence a successful result.

The provider budget guard caps observed NVIDIA/Nemotron requests at **20/minute
and 1,000/rolling day**, with shared atomic state across guarded processes. Requests
from uninstrumented clients remain outside its accounting; allow for total account
usage. Live model evaluations are opt-in and bounded.

Useful operator commands:

- `/poseidon-logs LOG_ID`: read bounded saved operation evidence.
- `/poseidon-end`: end the chat's sandbox while preserving work and settings.
- `/poseidon-resources`: inspect resource-governor diagnostics.
- `/agent-audit`: inspect registered tool executors and admission counters in the contract-enabled bundle.

Details: [contracts](docs/AGENT_CONTRACTS.md), [authority](docs/AUTHORITY.md),
[resource governance](docs/RESOURCE_GOVERNOR.md),
[implementation status](docs/IMPLEMENTATION_REPORT.md), and
[historical evaluations](docs/AGENT_EVALUATION.md).

## Evaluate prompt changes

The [offline benchmark](benchmarks/prompt_effectiveness/README.md) freezes prompts,
original requirements, starting artifacts and environment, archives review evidence,
and compares matched task outcomes. Different models, permissions, runtime, inputs
or requirements invalidate a prompt-only comparison. Critical workflow failures
block readiness even when visual scores are high. Repeats are grouped by task;
small samples do not establish general improvement.

The locally installed candidate is `grilling-default-v4`, with `evidence-v3` saved
as its matching prompt baseline. The [latest tuning](docs/usage-reviews/2026-11-01-evidence-v3.md)
targets review accuracy, ordinary boundary states and reuse of validation evidence
based on the calculator and editor sessions. Ten cases cover discovery, question recovery,
precise fixes, user journeys and transfer tasks. No controlled product-effect delta
is claimed. Historical project reviews remain separate from scored benchmark runs.
Snapshots and run artifacts are local and ignored by Git; setup/scoring makes no
model requests.

## Verify the repository

```sh
python3 -m unittest discover -s tests -v
node --test tests/test_agent_contracts.mjs tests/test_reliability_plugin.mjs tests/test_workspace_plugin.mjs tests/test_resource_governor.mjs tests/test_provider_budget.mjs
python3 .opencode/runtime/skillctl.py validate
bash -n install.sh
```

Resource-governor integration tests need macOS process-metric access. A restrictive
execution sandbox may block those metrics, which deliberately fails admission
closed. Deterministic tests need no provider requests. Passing infrastructure tests
does not establish every live agent or GUI outcome. See [validation notes](docs/validation.md).

### Folders without Git

The workflow also supports ordinary folders and workspace roots containing
multiple repositories. Sandbox settings, session state, logs and test evidence
live in `.opencode/workspace/`; no `git init` is needed. Git projects continue to
use their shared Git directory. A new Git repository does not need a first commit.

Without Git, snapshots enumerate ordinary files and exclude credentials, agent
configuration and common dependency/build folders (`node_modules`, virtualenvs,
cache, `dist`, `build`, `coverage`, `.next`). Symlinks are rejected rather than
followed. Git ignore rules apply in Git projects; the ordinary-folder fallback
uses these fixed exclusions instead. Docker and operator-configured test commands
are still required for sandbox testing.
