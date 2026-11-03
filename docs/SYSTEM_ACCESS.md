# Agent system access

The user-authorized access matrix is:

| Agent | Remote administration | Remote observations | Local development writes |
| --- | --- | --- | --- |
| Poseidon | Native host shell | Yes | Yes |
| Team Lead | Native host shell | Yes | Yes |
| Researcher | No | `system_access` | Assigned source and isolated commands |
| Maintainer | No | `system_access` | Assigned source and isolated commands |
| Coder | No | `system_access` | Assigned source and isolated commands |
| Reviewer | No | `system_access` | Assigned source and isolated commands |

Poseidon remains the sole primary/delegator. Administration capability does not
independently authorize deployment, production data changes or unrelated external
actions; the current user request and repository instructions determine the task.
Top-level host shell is unrestricted by the native file-edit scope checks and can
use existing SSH credentials, SQL clients, HTTP APIs and administrative CLIs.

## Connections

The trusted broker reads `~/.config/opencode/system-access.json` (or the operator's
`OPENCODE_SYSTEM_ACCESS_CONFIG` override). Copy the portable
[`system-access.example.json`](../.opencode/runtime/system-access.example.json)
and configure existing SSH aliases; keep deployment-specific profiles and secrets
out of this repository. `system_access` with `action: connections` lists profile
names without credentials. Authentication and server privileges still come from
the SSH account and installed server-side clients; this update creates no remote
accounts or grants.

SSH uses the existing user config explicitly, batch mode, strict known-host checks,
and no agent or port forwarding. Profiles may describe PostgreSQL connections by
an existing local (`local_env_file`) or remote (`env_file`) application environment
file and variable name, without copying the password into a profile.
The broker reads that value in the appropriate location and passes the connection as process
environment rather than command arguments. Use only trusted application environment
files; they are parsed as key/value text and never sourced as shell code.

## Remote read operations

Assignments involving infrastructure include `system` in `sourceTypes`:

```json
{"action":"server.service","profile":"dallas","service":"jenkins"}
{"action":"postgres.columns","profile":"oslo-configured","schema":"public","table":"Items"}
{"action":"rabbitmq.queues","profile":"oslo-configured"}
{"action":"jenkins.config","profile":"production","job":"Oslo"}
```

The tool supports server status/process/container/service/log observations;
PostgreSQL/MySQL table lists, columns and bounded rows (with optional selected
columns, equality filters and batched-value filters); RabbitMQ status, queues,
exchanges, bindings and virtual hosts; and Jenkins jobs, configuration, build
metadata and logs. Remote SQL is generated from validated identifiers inside a
read-only transaction. Workers cannot supply arbitrary SQL, shell commands,
Jenkins scripts/build triggers, or RabbitMQ publish, consume, acknowledge or purge
operations. Worker native webfetch uses the same broker and an explicit
public-read hostname allowlist, including redirect checks and no environment
proxy/cookies. It cannot reach Jenkins/control-plane URLs through a fetch bypass.
Operators can configure public_read_hosts only for trusted public read services;
infrastructure access stays on the fixed service operations. Remote mutations go
to Poseidon/Team Lead. Least-privilege remote
accounts provide an additional service-side boundary where available.

## Local commands and services

All roles have native edit capability, subject to assignment scope, exclusions,
protected configuration/credential paths, symlink checks and existing UI brief
requirements. Workers need an assigned task before writing local source or
invoking local development commands. Reviewers and researchers change source only
when their assignment calls for it.

```json
{"action":"local_command","command":"python3 -m unittest discover -s tests","timeout_seconds":120}
```

On Linux, the command runs through Bubblewrap with a fresh network, PID, IPC and
mount namespace, cleared environment, temporary HOME, and no host credential or
service-socket mounts. The project is read-only except assigned paths; protected
control files, credential files, exclusions and existing socket/FIFO paths are
masked. No unrestricted shell fallback exists. Existing named-file scopes must
exist; create new files through native edits first. Local development servers and
tests can run together within the command's isolated namespace. Package downloads,
host service management and operations requiring credentials belong to top-level
agents. Local commands do not inherit the host's Git control directory.

For an already running local development service, an operator may configure a
`local_http` profile with `development_only: true`, an HTTP loopback-IP origin,
and explicit permitted path prefixes. Requests can write to those local services,
but cannot follow redirects or use environment HTTP proxies. Do not configure
production tunnels, Vite production proxies, the OpenCode control API, or any
service that forwards these requests to remote infrastructure. The local profile
is an operator trust decision; a loopback address alone does not prove the
application uses development data. No such write profile is enabled automatically.

```json
{"local_http":{"dev-api":{"development_only":true,"origin":"http://127.0.0.1:8000","paths":["/development/"]}}}
```

Docker testing remains available to Poseidon and Team Lead, including image/test
configuration and cleanup. Workers may inspect Docker settings/status but run
local checks through the isolated command runner; they cannot use a configured
remote Docker daemon as a write bypass. Bubblewrap failure, missing clients,
SSH authentication failure or insufficient remote privileges are reported; none
silently enables broader access. Role budgets, source-ID receipts and handoff
validation also apply to these tools.
