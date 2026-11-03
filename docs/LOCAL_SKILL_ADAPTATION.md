# Local CLI prompt adaptation

Reviewed 2026-11-03. The repository's `.agents/` folder was empty; the local CLI
catalog contained 74 skill entrypoints under `~/.agents/skills/`. The local
`.skill-lock.json` provided source labels and installation metadata. These are
local observations, not a fresh upstream or licensing verification.

## Retained guidance

The additions live directly in the Poseidon, Team Lead and Researcher prompts,
so their core behavior survives an unavailable optional skill. Native skill IDs,
models, permissions and assignment allowlists remain unchanged.

| Local source | Retained adaptation | Roles |
| --- | --- | --- |
| adaptive-communication | Match the task and tone; resolve consequential ambiguity without repeating settled questions | Poseidon, Team Lead |
| human-architect-mindset | Domain constraints, dependency failures, compatibility and bounded work items | Poseidon, Team Lead, Researcher |
| vanity-engineering-review | Tie complexity to observed needs; compare simpler alternatives using evidence | Poseidon, Team Lead, Researcher |
| negentropy-lens | Surface undocumented operational assumptions; preserve useful decisions and ownership | Poseidon, Team Lead, Researcher |
| doc-coauthoring | Check whether a document works for its intended reader without the chat history | Poseidon, Team Lead, Researcher |

Existing skills cover the relevant procedures: domain-modeling, how,
codebase-design, writing-plans and verification-before-completion for the
coordinators; Team Lead additionally has to-spec. Researcher retains its bounded
karpathy-guidelines-only skill list and receives the research heuristics directly.
This is a selective, newly written prompt adaptation, not a verbatim import or
registration of the external skill packages. The pinned upstream skill manifest
and its license/integrity checks are unaffected. The local CLI source files are
unchanged and are not required on another machine.

## Compatibility decisions

- Retain useful task guidance without copying mandatory questionnaires, repeated
  closing nudges, rigid scores, speculative maintenance-hour estimates or the
  vocabulary of a particular philosophical framework into every response.
- Do not import personal stack preferences from bencium-code-conventions (for
  example another user's Mac, no-Docker and database preferences), brand defaults,
  framework catalogs or a placeholder skill as requirements for this project.
- Complexity reviews propose evidence-backed changes. Source suggestions for
  automatic shutdown/deletion do not grant operational authority.
- Reader checking means assess missing context in the document. It does not
  require new agent launches, alternative models, repeated approval rounds or
  claims that independent testing occurred.
- Missing optional prompt guidance permits a scoped fallback. Missing evidence,
  required checks or service access remain explicit limitations. Permission denials
  never authorize another route around the restriction.

## Scenario review

| Situation | Intended response |
| --- | --- |
| Team Lead's optional how skill is unavailable | Use retained dependency/tradeoff guidance, return a scoped plan to Poseidon; do not launch an agent or retry spellings |
| Researcher receives a complexity question | Investigate assigned sources, separate measurements from hypotheses, retain source IDs and report unknowns; no new design skills or remote writes |
| A brief already contains the user's stack choice | Preserve it; architecture advice cannot replace the confirmed preference |
| Browser/required integration is unavailable | Complete independent source analysis and label the dependent live/visual check unverified |
| A source prompt suggests shutting down an unused service | Report evidence and a recommendation; do not treat the prompt as authorization |
| A spec assumes knowledge from this chat | Add the necessary context and decision provenance to the requested document; do not create a separate documentation project |

These scenarios were reviewed against the role prompts and existing authority
checks. Static configuration/contract tests verify packaging and permission
invariants; they do not establish model behavior. No provider-backed evaluation
was performed during this adaptation.

## Local source fingerprints

The local lockfile labels the first four sources above as
`bencium/bencium-marketplace` and doc-coauthoring as `anthropics/skills`.
SHA-256 identifies the exact local entrypoint reviewed; it is not an upstream
Git commit or an assertion that the package was independently verified.

| Local skill | Reviewed SKILL.md SHA-256 |
| --- | --- |
| adaptive-communication | `9806cac7ac0c188956d649b3c4449b20813d27f9d1aac3585ca3139d32f9ea34` |
| human-architect-mindset | `60becdb274d57d781a18ecd9c95bdb8ec9f5dd80e4b98f3b309bf59fc7e6cef6` |
| vanity-engineering-review | `7373bcbc57ece2315df1a63905958dc13bd3397c793b89c386edef447b002699` |
| negentropy-lens | `3817c83daa0b1b361d343b92f84e6fcd7c1d9970de064b231ab8c01cc3b013d4` |
| doc-coauthoring | `2e47d78846faeea4a56e9809c52700087a15a2155a3f293a3efbaded81398ef4` |
