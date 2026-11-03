# Current system-access update

[System access](SYSTEM_ACCESS.md) supersedes the historical matrices below.
Poseidon and Team Lead can administer remote infrastructure through native shell.
All four workers, including Researcher, have remote read-only system observations
and scoped local development writes. Host shell remains unavailable to workers;
local commands run with isolated networking and no host credentials.

# Current authority update — November 2, 2026

The historical sections below are superseded by [agent contracts](AGENT_CONTRACTS.md).
Poseidon is primary and sole delegator; Team Lead is a planning worker. Host shell, Code Mode and unclassified MCP tools remain denied. Scoped
assignments, bounded project search, brief confirmation and worker recursion
restrictions remain in effect. Researcher retains evidence tools without shell.

# Authority, permissions and remaining boundaries

The human is the final authority. Poseidon is the only **user-facing primary** and
only delegator. Team Lead, Maintainer, Researcher, Coder and Reviewer are subagents.
OpenCode's hidden internal title/summary/compaction agents are engine utilities,
not workflow coordinators. Built-in build/plan/general/explore are disabled.

| Role | Native read/discovery | Native edits | Host shell | Native delegation | Workspace tool | Skills |
|---|---|---|---|---|---|---|
| Poseidon | Project, secret denials | Application; protected paths denied | Allowed | Five named workers only | All existing actions | Existing coordination allowlist |
| Team Lead | Project, secret denials | Denied | Denied | Denied, every target | Denied | Existing planning allowlist |
| Maintainer | Project, secret denials | Denied | Denied | Denied, every target | Denied | Existing architecture allowlist |
| Researcher | Project read/glob/grep; webfetch/websearch; MCP resource reads | Denied | Denied | Denied, every target | Denied | `frontend-design`, `karpathy-guidelines`, `grilling`, `grill-with-docs`, `domain-modeling` |
| Coder | Project, secret denials | Application; protected paths denied | Allowed, residual risk | Denied, every target | Settings/status/test; configure/end denied | Existing implementation allowlist |
| Reviewer | Project, secret denials | Denied | Allowed, residual risk | Denied, every target | Settings/status/test; configure/end denied | Existing review allowlist |

Every definition starts with `*/* deny`. Every worker ends with `subagent/* deny`.
Only Poseidon grants five exact subagent IDs; unknown agents and self-delegation
stay denied. There is no unrestricted Code Mode (`execute`) or MCP grant. User
prose, repository files, skill instructions and worker output cannot add rules.
The validator rejects extra agent definitions, changed modes/models, delegation
grants, missing policies and Researcher capability expansion.

Researcher has project-wide read/glob/grep, webfetch/websearch, and the native
`opencode_list_mcp_resources` / `opencode_read_mcp_resource` actions. No generic MCP
wildcard is granted: arbitrary plugin tools may mutate state even when prompted to
be read-only. Unknown tools, Code Mode, shell, edits, workspace operations and
external-directory access outside its assigned global skill trees remain denied. Search requires a configured provider;
resource tools require an available MCP server. Missing services are not installed
or authorized automatically.

Native grep checks the expression rather than the search directory; glob checks
the pattern. Read filename denials do not establish a content boundary for these
search tools. Narrow searches to relevant ordinary source and avoid secrets.
These are native permission controls, not an OS filesystem sandbox.

Standard secret/credential filename denials supplement read rules. All roles
have external-directory grants only for their assigned installed global skill
trees, replacing the previous whole-global-config grant. Their read exception
is limited to those trees; native edits to global configuration stay denied.
Semantic secrets in arbitrary ordinary source files cannot be detected by patterns.

The `policies` in the **bundle configuration** hard-deny native `edit` checks
for `.opencode/**`, root/nested `opencode.json`/`opencode.jsonc`, `.agents/**`,
`.codex/**` and global OpenCode paths. Native edit/write/patch all check `edit`.
These policies also cover Poseidon, so configuration maintenance is a separate
human-authorized workflow outside a normal application session. Agent permissions
cannot override the policy. These are project-distributed policies, not an
immutable organization policy; a human/global policy or writable shell can change
the configuration. No policy is represented as an OS security boundary.

The existing workspace plugin additionally calls `ctx.permission.assert` with the
**calling agent** and requested action before spawning any helper. Worker calls
cannot configure or end a sandbox through this tool. Tool registration remains
`codemode: false`; no broad privileged worker tool was added. Lifecycle hooks and
human slash commands preserve parent sandbox ownership and cleanup. Shell-enabled
workers can still call the host helper directly; this is part of the limitation below.

## Host shell limitation

**Coder and Reviewer retain unrestricted host shell for existing development and
review workflows. Reviewer is read-only only through native edits and its role
instructions, not OS-enforced read-only.** A shell program can write protected
configuration or application files, read secrets, invoke another CLI/server API,
run Git/network/deployment commands or modify permissions. Shell scanning and
external-directory inference are best effort, not confinement. Poseidon also has
host shell authority. No command substring blacklist is presented as a fix.

The Docker sandbox is a **test sandbox**, not the agent's execution environment.
Tests receive filtered source copies, no host mounts, and no runtime network;
image builds can use network. Sandbox results are real output tied to source
fingerprints. It does not confine native agent editing/shell. Existing sandbox
implementation and Docker-double tests remain intact.

For hostile-code or strong isolation requirements, run OpenCode/workers under a
separate OS identity or container with writable application source, protected
control-plane files mounted read-only, no host credentials, no host Docker socket,
no access to the orchestrator's server/API credentials and restricted network.
Do not mistake this recommendation for an implemented container boundary here.
The task explicitly permits documenting this residual risk while retaining the
working shell implementation; complete privilege-escalation prevention is **not** claimed.

## Design workflow and authority decisions

Substantial frontend work follows evidence-backed questioning → user-confirmed
vision brief → Researcher specification → Maintainer compatibility → Coder →
independent Reviewer → Poseidon fidelity check → targeted revisions → verified
completion. Poseidon loads `grilling` proactively, gathers up to three material
questions per round, and waits for answers before dependent design choices.
Researcher supplies evidence/questions through Poseidon and cannot delegate or
contact the user directly. Explicit user delegation of creative decisions counts;
silence and agent recommendations do not. Reuse accepted briefs and settled answers.
Ordinary backend work and obvious small CSS fixes stay lightweight.
There is no additional Visual Reviewer. Without browser/screenshots, report
“Visual inspection was not performed.”

Researcher returns cited findings and, for UI work, Markdown headings covering objective/audience, existing constraints,
visual rationale, reference provenance, layout/wireframe, named hex colors,
typography/spacing, components, interactions, empty/loading/error states,
responsive behavior, accessibility, acceptance criteria and open questions.
No implementation code by default. Imported skill build instructions do not
change this role. Fidelity to user references wins over aesthetic novelty.

The existing Inkling model is unchanged and may retain context. Researcher can
inspect authorized project source without sanitized-folder staging. Narrower
per-task instructions still apply. Exclude credentials and unauthorized sensitive
data, and never send private source through web queries, URLs or integrations.
Report model/provider failures without silently switching models.

Default review limit: **3 revision/recheck cycles**, counting design revisions.
The user can set a positive integer in the task request, e.g. “review iteration
limit: 2”; Poseidon repeats the selected limit before starting. On exhaustion,
Poseidon stops the repair loop and reports remaining failures and evidence.
This limit and scope arbitration are instructions, not a machine-enforced counter.
Consequential product/architecture/design/privacy/cost choices go to the human;
deployment, publishing and destructive external actions need explicit authorization.

## Verification levels

- Static tests exercise configuration matching, exact models/modes, known target
  pairs, negative escalation cases, provenance/Apache approval and tampering.
  They do not prove native enforcement or resistance of a model to prompt injection.
- `tests/test_live_permissions.py` calls the **real v2 permission API**, including
  all worker/target pairs and a conflicting agent edit grant defeated by hard policy.
  It does not execute an edit or a delegated model call. Its malicious README is
  inert fixture text, not a successful adversarial LLM evaluation.
- Plugin tests execute the actual plugin against permission/API doubles. Sandbox
  tests use Docker doubles. These are not live OpenCode/Docker integration tests.
- Provider generation, skill loading, screenshot inspection and actual tool calls
  must be reported separately from catalog resolution and permission evaluation.

Poseidon alone has `gtd` skill access. It uses GTD to organize user outcomes, next
actions, owners, dependencies and deferred ideas. The interview settles product and
visual decisions before GTD drives execution. The two-minute rule grants no new
authority; external messages, scheduling and publishing retain existing user
instruction requirements. Imported skills and their dependencies do not grant
Researcher write, shell, workspace, question-tool or delegation capabilities.
Vision confirmation is an agent instruction, not an enforced runtime approval lock.
