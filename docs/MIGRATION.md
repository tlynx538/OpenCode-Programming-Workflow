# Safely update an existing installation

The repository bundle and an installed bundle are independent. Both installers
copy missing files and **never overwrite existing files**. Running the installer
on an old bundle alone is not a migration: the old Poseidon permissions, validator
and SOURCES manifest would remain. Do not start chats using such a mixed bundle.
No installed configuration was changed by this implementation.

1. Finish/stop active OpenCode chats. From this repository, validate the source:

   ```sh
   python3 .opencode/runtime/skillctl.py validate
   ```

2. Select the actual installation and generate a read-only difference inventory:

   ```sh
   installed='/absolute/path/to/project/.opencode'
   # For global installation instead: installed="$HOME/.config/opencode"
   python3 .opencode/runtime/skillctl.py compare-install "$installed" > /tmp/poseidon-install-comparison.json
   ```

   Inspect `DIFFERENT`, `MISSING`, `SYMLINK_REVIEW`, `TYPE_CONFLICT` and the
   `existingJsonc` flag. The command writes no installation files and returns no
   installed file contents or credentials. Resolve symlinks/type conflicts manually.
   It compares managed inventory; it does not remove unrelated local files.

3. Build a separate candidate from the complete new bundle:

   ```sh
   staging=$(mktemp -d)
   candidate="$staging/opencode"
   cp -R .opencode "$candidate"
   ```

   Review old/new definitions and configuration locally. Manually merge intentional
   local customizations into the candidate. Preserve provider connections, MCP/plugin
   settings, user skills and unrelated files deliberately; never paste credentials
   into a model conversation or copy a credential database into the candidate.
   For an existing JSONC, manually port its intentional settings into the
   candidate's canonical `opencode.json` while keeping the original JSONC in the
   untouched installation/backup. Keep only the reviewed JSON active in the
   candidate; do not copy a competing JSONC beside it. This preserves the original
   for rollback and lets the strict bundle validator inspect the effective candidate
   JSON. Validate discovery with the actual CLI as well.

   Merge these changes as one unit: six agent definitions, `default_agent`, disabled
   built-ins, ordered permissions, protected `tool.use` policies, workspace plugin,
   runtime validator and complete SOURCES/provenance/skill trees. Preserve existing
   model assignments. Extra custom coordinators/worker grants need separate human
   review; the strict bundle validator intentionally rejects unexpected native roles.
   Do not resolve validator failures by simply changing hashes or removing checks.

4. Validate the candidate **before activating it**:

   ```sh
   python3 "$candidate/runtime/skillctl.py" validate
   python3 .opencode/runtime/skillctl.py compare-install "$candidate" > /tmp/poseidon-candidate-comparison.json
   ```

   Review all intentional remaining differences. Run the repository Python and
   Node suites, and use an isolated OpenCode server to inspect candidate agent
   discovery/permissions. Keep application-specific tests too. A successful source
   validation alone does not certify a customized installed bundle.

5. After reviewing the candidate, back up and activate it while OpenCode is stopped.
   These commands intentionally change the selected installation, so the human
   performs them only after accepting the exact reviewed candidate:

   ```sh
   backup="${installed}.backup-$(date +%Y%m%d-%H%M%S)"
   test ! -e "$backup"
   test ! -e "${installed}.candidate"
   cp -R "$candidate" "${installed}.candidate"
   mv "$installed" "$backup"
   mv "${installed}.candidate" "$installed"
   ```

   Ensure `${installed}.candidate` does not already exist before the copy. The backup
   retains local files; keep it until validation in the installed environment passes.
   To roll back, stop OpenCode, move the new installation aside and restore the backup.
   Windows users use the same staging/review/backup process with PowerShell
   `Copy-Item`/`Move-Item`; `install.ps1 -DryRun` continues to preserve existing files.

6. Restart OpenCode completely. Watched configuration usually reloads automatically,
   but a full restart avoids retaining old sessions, plugins or permissions. Start
   a **new chat**, verify Team Lead is the default for this bundle and Researcher appears as a
   subagent, then inspect the OpenRouter model catalog. Never assume an old session
   or the previously running global installation has picked up repository changes.
   No global CLI upgrade or provider/model reassignment is required.

For a fresh installation, the existing commands suffice:

```sh
./install.sh --project /path/to/project --dry-run
./install.sh --project /path/to/project
# Or ./install.sh --global after reviewing that destination.
```

Example request to Poseidon:

> Design a community garden volunteer dashboard using this sanitized mock brief.
> Keep the existing routes and API, specify desktop/tablet/mobile behavior, and use
> Researcher for the handoff before Coder implementation. Review iteration limit: 2.

Poseidon delegates a bounded brief to `researcher`, asks Maintainer about fit,
consolidates the specification, routes implementation to Coder and independent
review to Reviewer, then assesses fidelity using available visual evidence.

## Researcher rename

The former `ui-designer` role is now `researcher`. Migrate Poseidon's delegation
rule, the agent file, skill matrix and runtime validator together. Remove the old
`agents/ui-designer.md` from the staged candidate after preserving any customizations;
leaving it creates an unexpected seventh agent. The installer preserves existing
files and does not remove stale agents. Restart into a new chat after activation.
Project source reads/search and web research replace the sanitized-folder-only
restriction. Generic mutating integration tools and shell remain denied.

## November 1 reliability authority migration

This is an intentional authority/permission change: default_agent and the sole primary move from Poseidon to Team Lead; Poseidon becomes the design worker; all agents lose host shell and runtime sandbox configuration. Researcher loses design/interview skills. Operator-configured Docker testing and the fixed-argv log command preserve verification/log access. Do not merge only an agent prompt.

Review and stage the six definitions, opencode.json policies/default, skills/SOURCES.json role matrix, workspace plugin, runtime/agent-contracts.mjs, runtime/reliability-plugin.mjs and runtime/agent-limits.json as one bundle. Preserve provider settings, unrelated plugins and existing project sandbox state. Validate the complete staged bundle and run its deterministic tests before selecting it. The installer will not overwrite an existing installation. No existing global installation was modified for this assignment.

A global legacy poseidon-workspace plugin may coexist with the local installation-specific plugin ID. The local copy detects and reuses its workspace tool and installs the new guards around it. An attempted plugin.use deny did not remove the legacy plugin from live discovery and was removed; enforcement does not rely on that ineffective policy. Check actual plugin/command discovery, not just file content. An updated global copy yields to a project-local bundle to avoid duplicate infrastructure.

After choosing the reviewed installation, restart/load a fresh project and chat. Confirm Poseidon primary and the new agent_contracts/project_search tools plus confirm-brief/agent-audit commands. See AGENT_CONTRACTS.md for operator brief confirmation and evaluation-only commands.

## November 2, 2026: restore Poseidon and development tools

This update supersedes the November 1 Team Lead/no-host-shell profile. Apply the
configuration, all six agent definitions, runtime contracts/limits and plugin
together: Poseidon is the primary delegator, Team Lead becomes a planning worker,
and handoffs route to Poseidon. Workers retain their existing skill lists and
models. Permitted native tools are exposed directly with Code Mode disabled.
Host shell remains denied.

The installers never overwrite existing files. Inspect
`python3 .opencode/runtime/skillctl.py compare-install DESTINATION` output, back
up custom settings, and copy reviewed files together when updating a profile.
Reload OpenCode after installation and
select Poseidon for an existing session; changing default_agent affects new
sessions and does not rewrite saved session selections.

## Non-Git workspace support

Install `runtime.py`, `sandbox.py`, `logs.py`, `workspace.py` and
`reliability-plugin.mjs` together and reload OpenCode. Ordinary folders now store
settings, operation logs, session state and evidence in `.opencode/workspace/`.
Git projects retain their shared Git storage. Existing non-Git sessions can
continue; they no longer fail merely because the workspace lacks a repository.
Unconfigured tests report the missing configuration; they do not claim a pass.

## Role-based system access

Install all six agent definitions, runtime contracts/validator, system-access.py,
reliability-plugin.mjs and the workspace plugin together. Configure the private
system-access.json beside the global OpenCode configuration; the portable example
contains no real hosts or credentials. Reload OpenCode. Poseidon/Team Lead now
have host shell; all workers have remote read-only system_access and local-write
capabilities. Worker local commands require Linux Bubblewrap. Existing worker
tasks need system in sourceTypes when investigating infrastructure. See
SYSTEM_ACCESS.md for operation names, authentication prerequisites and local-only
service profiles. No production deployment or database mutation is part of this
configuration update.
