# Session tool-access review — November 2, 2026

Reviewed local session `ses_e621d2d04ffeiKYZop3W15pLvy` and its two child
sessions using a disposable copy of the OpenCode SQLite database. No messages
were sent and no original session or installed configuration was changed.

Observed failures:

- The session selected Team Lead. The repository explicitly configured it as
  default/primary and Poseidon as a non-delegating worker.
- Researcher received “Tool is not available for this request: project_search”
  and attempted unavailable Code Mode after that failure.
- Reading the workspace root failed with “Invalid scope path”: the relative
  path normalizer converted the project root to an empty string.
- Scoped glob calls were rejected, and the root handoff cited source IDs absent
  from its ledger. Tool output and subsequent user prompts need stable evidence
  representation and source IDs.
- Docker preparation was unavailable because the workspace root was not itself
  a Git repository. An eight-step worker budget was also exhausted. These are
  separate operational limits, not proof of a missing permission.

The repair makes Poseidon the primary and sole delegator, transfers coordinator
budgets and workspace permissions, and routes all handoffs back to Poseidon.
Permitted registered tools explicitly use `codemode: false`; this makes their
native exposure independent of the denied Code Mode entry point. See the
[OpenCode V2 tool documentation](https://dev.opencode.ai/v2/docs/tools/) and
[plugin API](https://opencode.ai/v2/docs/build/plugins/server/).

Root reads normalize to `.` while scope, protected paths and external symlink
checks remain enforced. Text-array results contribute ordinary text to the
source ledger, and user follow-ups preserve retrieved source IDs. Regression
coverage checks these behaviors, worker delegation denials and shell denial.

This does not enable unrestricted shell, install missing services, expand task
scope, increase Researcher budgets, or provision Docker for multi-repository
workspace roots. The reviewed business task was not rerun against a model;
validation uses deterministic tool tests and the real OpenCode permission API.

The subsequent non-Git workspace update removes the Git prerequisite from
sandbox settings, logs, source snapshots and test evidence. Ordinary folders
use `.opencode/workspace/`; Docker availability and explicit test configuration
remain separate requirements. See the README for source filtering behavior.

## Follow-up: session ses_e61ef2cf5ffe2Hu9QKypE5hPez

The first Researcher was launched in the background. The wrapper treated the
launch acknowledgment as completion, recorded a PARTIAL fallback and closed the
worker before its first model step. Closed-state context then removed read/search
tools. This was a lifecycle error, not a missing native read grant.

A foreground follow-up read both assigned files but an exact-file glob was denied
by the project-wide-only discovery check. Its handoff attempts then used a wrapper
string, changed a null brief version to 1, and cited filenames instead of retrieved
source IDs. Attempts to propose a brief as Researcher were correctly denied.
Large coordinator status output was also truncated by OpenCode.

The repair waits for validated worker completion, supports bounded glob discovery
inside assigned scope, returns a ready-to-fill submit template and allowed actions,
keeps status compact, and adds evidence source-ID receipts to retrievals. Tests
replay background dispatch through a successful cited worker handoff, named-file
and directory discovery, protected/excluded paths, and malformed handoff rejection.
Existing role boundaries are retained.
