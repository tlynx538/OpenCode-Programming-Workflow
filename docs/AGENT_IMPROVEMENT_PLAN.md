# Agent reliability improvement plan — November 1, 2026

## Baseline and scope

This is a configuration/infrastructure improvement, not model training. Historical
letter grades remain Coder B+, Maintainer B, Poseidon B, Team Lead B (low
confidence), Reviewer C+, Researcher D. Samples are unequal. Preserve the dated
observations in AGENT_EVALUATION.md; a passing configuration test is not a model
behavior pass.

Before editing, the full `.opencode` tree and its file hashes were captured in a
private temporary snapshot. A sanitized inventory is retained under
`docs/evaluations/2026-11-01-baseline.json`. The working tree already contained
extensive user changes; those were preserved. No commit, push or global-install
migration was requested or performed.

Installed CLI: OpenCode v2.2.5. Repository default: Poseidon primary, five workers;
only Poseidon delegated. Coder, Reviewer and Poseidon had host shell access.
Researcher could load frontend-design, grilling, grill-with-docs, domain-modeling
and karpathy-guidelines. Runtime governor admitted one worker/one heavy tool,
one delegation level, four queued jobs and 15-minute cooperative work timeouts.
Per-role model-step limits and pre-execution research budgets were absent.
The polling evaluator could detect a tool overrun only after it happened.

The global installed bundle differed from the repository. Live discovery exposed
a duplicate `poseidon-workspace` plugin ID: global active, project rejected.
Consequently older disposable-project runs verify their recorded outputs, but do
not establish that their project-local plugin implementation was active. Actual
agent definitions did resolve from the project. No provider credentials were read
or copied. Existing models/providers were retained. No 1,000-request constraint
was found in repository/global JSON; the new local Reviewer guard caps model
requests at 1,000/day per plugin location, not across an entire provider account.

## Failure → intervention → measurable regression

| Failure/evidence | Symptom | Cause versus hypothesis | Intervention | Regression / acceptance |
|---|---|---|---|---|
| Historical Researcher runs: 9 attempts for 8-call budget | No findings before interruption | Demonstrated: polling detects excess afterward; prompt obedience unreliable | Serialized reservations before executor; source/skill gates; final submit slot; native steps; runtime deadline | Concurrent admission test: at most 7 work calls plus final handoff in 8-call task; separately count denied attempts |
| Researcher 300-word handoff exceeded limit | Long critique hides decision | Demonstrated instruction noncompliance; model-specific explanation unproven | Validate accepted human prose/claims/findings; bounded structured envelope; fail-closed PARTIAL fallback | Reject oversized submission; published accepted handoff within configured limit |
| Researcher called frontend-design before intent confirmation | Agent aesthetic framing leaks into findings | Demonstrated available permission; effect on output is plausible | Remove all design/interview skills from Researcher; only task-approved karpathy guideline | Native matrix + executor-spy tests: unauthorized skill executor never runs |
| Researcher labeled non-premium as fact | Unsupported user requirement | Demonstrated output error; not evidence about all runs of that model | Typed claims, retrieved source ledger, exact excerpts, independent critique; canonical briefs require user command | Reject fake source/quote; reviewer must check entailment and context; source existence alone is insufficient |
| Researcher proposed proxy test/nonexistent unittest API | Proposed test did not prove behavior | Demonstrated failure; broad coding ability unproven | Keep runnable implementation with Coder; require initial state, trigger, observable allowed/rejected result | Preserve paused-guard fixtures and independent 32-case truth-table check |
| Reviewer overstated Critical | Severity exceeded demonstrated impact | Demonstrated output error | P0–P3 criteria, required evidence/impact/confidence/remedy; P0 immediate-danger field | Reject unsubstantiated P0 and FAIL based only on preference |
| Reviewer 120-second review ended without verdict | No bounded decision | Demonstrated; provider latency versus investigation cause uncertain | Native steps/deadline, verdict schema, deterministic INCONCLUSIVE fallback | Every published bounded review has a validated verdict; model completion scored separately |
| User preferences lost across handoffs | Correct code can still violate design | End-to-end fidelity not yet demonstrated | Immutable versioned brief in plugin storage; hash-bound operator confirmation; scoped Coder gates and stale-version checks | No self-confirmation; UI writes require current confirmed brief; revision cannot silently drop prohibitions |
| Host shell in Coder/Reviewer | Native edit deny could be bypassed | Demonstrated capability, not a recorded malicious act | Deny shell/Code Mode/unknown tools to every role; configured Docker verification only; bounded literal local search replaces native grep | Native permission tests + executor spies; Reviewer cannot edit via another registered route |
| Duplicate project/global plugin ID | New definitions with old runtime | Demonstrated live plugin status | Installation-specific plugin ID; updated global copy yields to local copy; local guards reuse an existing global sandbox tool | Compatibility regression; verify actual commands/plugin status before model evaluation |
| Broad preliminary research assignment | Named question but five approved files | Demonstrated harness contract error | Exact file scope derived per case; frozen bundle; retain preliminary failures | Out-of-scope read denied before execution; report exact per-case hashes |
| Orchestration ownership differs from requested model | Poseidon owns all delegation | Intentional migration, not a defect in previous design | Team Lead primary/sole delegator, Poseidon design authority, other workers bounded | Every subordinate target denied; only Team Lead's five exact targets allowed |

## Public architectural references

These are reference methods, not imported skills or access to proprietary prompts:

- [Microsoft Researcher documentation](https://learn.microsoft.com/en-us/microsoft-365/copilot/researcher-agent): scoped source-backed research and clarification.
- [Microsoft Critique](https://support.microsoft.com/en-us/microsoft-365-copilot/use-critique-with-researcher-agent-in-microsoft-365-copilot): a distinct review pass motivates reusing Reviewer for material claim/source critique. It does not disclose Microsoft's internal budgets or implementation.
- [K-Dense scientific-critical-thinking](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/scientific-critical-thinking): extract evidence before judgment; separate observation, inference and missing reporting.
- [market-research-reports](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/market-research-reports): define decision scope, source/claim ledgers and statement classes.
- [peer-review](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/peer-review): specific, constructive, proportional critique.
- [paper-lookup](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/paper-lookup): source identity/provenance and discipline-appropriate retrieval; no database adapters or credentials adopted.
- [literature-review](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/literature-review): reproducible scope, conflicting evidence and actual citation checking; bounded discovery is not exhaustive synthesis.

All five upstream SKILL.md workflows were inspected. No K-Dense collection,
program, paid search service, image generator or dependency was installed/enabled.
Existing third-party skills and licenses remain byte-identical. Project code uses
thin contracts and policy gates rather than replacing those skills with summaries.

Implementation uses documented [V2 steps](https://dev.opencode.ai/v2/docs/agents/#steps),
[tool transforms, context/retry hooks, storage and cancellation](https://opencode.ai/v2/docs/build/plugins/server).
No legacy maxSteps/subagent_depth option or invented final-output hook was added.

## Controlled cycle and limits

Historical observations and a nine-case before run are retained. Preliminary after
runs exposed configuration/harness problems and a provider overload; they are not
quietly relabeled as successes. The final harness freezes a bundle once and uses
fresh disposable projects, identical case questions and a 60-second outer deadline.
Only the local test assignment supplies the stricter source contract.

Budget enforcement guarantees admissions, not that a model never attempts denied
calls. A runtime fallback is safe partial delivery, not task completion. A citation
substring check proves retrieval/provenance, not semantic entailment. Independent
source review is still required. Explicit UI-extension gates cannot classify every
possible product/design change hidden in general-purpose source. Trusted plugins,
the server operator and arbitrary user-authored secrets in otherwise normal source
remain outside these policy guarantees. Do not describe these controls as an OS
sandbox or universal prompt-injection immunity.

## November 3 runtime correction

Session `ses_e6198aafaffeFFRHBxyVZLHkFE` exposed overly strict handoff formatting,
short worker budgets, missing declared output on native tool replacements, and a
revision field mismatch. The current contract guide supersedes the earlier proposal
to reject long reports or every unmatched quotation. Preserve useful reports, label
unverified claims, keep independent critique, provide public contract help and
readable brief files, and use stable idempotent confirmation receipts.
