import { existsSync, realpathSync } from 'node:fs'
import path from 'node:path'
import { createHash } from 'node:crypto'
import reliability from '../../runtime/reliability-plugin.mjs'
import { Governor } from "../../runtime/resource-governor/governor.mjs"
import { fileURLToPath } from "node:url"
import { randomUUID } from "node:crypto"

const bridge = fileURLToPath(new URL("../../runtime/workspace.py", import.meta.url))

export default {
  id: "agent-reliability-" + createHash("sha256").update(import.meta.url).digest("hex").slice(0, 12),
  async setup(ctx) {
    // A project-local bundle owns this location. An updated global copy stays inert.
    const localEntry = path.join(ctx.location.directory, ".opencode/plugins/poseidon-workspace/index.js")
    if (existsSync(localEntry) && realpathSync(localEntry) !== realpathSync(fileURLToPath(import.meta.url))) return () => {}
    // Reuse an already registered legacy/global sandbox tool; install only the new guards.
    // This avoids duplicate sandbox prompt hooks and duplicate process monitors.
    if (ctx.tool.list && (await ctx.tool.list()).some(tool => tool.id === "poseidon_workspace")) return reliability.setup(ctx)
    const governor = new Governor()
    governor.start()
    const rootSession = async (sessionID) => {
      const seen = new Set()
      while (!seen.has(sessionID) && seen.size < 32) {
        seen.add(sessionID)
        const response = await ctx.session.get({ sessionID })
        const session = response.data ?? response
        if (!session.parentID) return sessionID
        sessionID = session.parentID
      }
      throw new Error("Cannot resolve the owning OpenCode session")
    }
    const logCommand = (identifier) => {
      if (!/^[a-f0-9]{32}$/.test(identifier)) throw new Error("Invalid log ID")
      // Fixed read-only command: never accepts arbitrary shell input or starts implementation.
      return ["python3", "-u", bridge, "--repo", ctx.location.directory, "follow-operation", identifier]
    }
    const invoke = (input, signal, progress, agentID = "team-lead") => {
      const recorded = ["session_start", "configure", "test"].includes(input.action)
      const payload = recorded ? { ...input, operation_id: randomUUID().replaceAll("-", "") } : input
      let stderr = "", publishing = false
      return governor.execute(["python3", "-u", bridge, "--repo", ctx.location.directory, "call"], {
        signal, input: JSON.stringify(payload), sessionID: input.session_id, agentID, taskID: payload.operation_id,
        cleanup: ["end_sandbox", "settings", "status"].includes(input.action),
        // Progress tails are bounded; no queued promises retain entire output history.
        progress: progress ? (index, chunk) => {
          if (index === 1) {
            stderr = (stderr + chunk.toString()).slice(-65536)
            if (!publishing) {
              publishing = true
              Promise.resolve(progress({ output: stderr })).catch(() => {}).finally(() => { publishing = false })
            }
          }
        } : undefined,
      }).then((result) => {
        if (result.truncated[0]) throw new Error("Workspace result exceeds governor output budget; see saved operation evidence")
        if (result.code !== 0) throw new Error(result.stdout || result.stderr || `Workspace operation exited ${result.code}`)
        return result.stdout
      })
    }

    const preparation = new Map()
    const remember = (owner, status) => {
      preparation.delete(owner)
      preparation.set(owner, status)
      while (preparation.size > 128) preparation.delete(preparation.keys().next().value)
    }
    await ctx.session.hook("prompt", async (event) => {
      const owner = await rootSession(event.sessionID)
      if (owner !== event.sessionID) return // Delegated agents share the parent's sandbox.
      remember(owner, JSON.parse(await invoke({ action: "session_start", session_id: owner })))
    })
    await ctx.session.hook("context", async (event) => {
      const owner = await rootSession(event.sessionID)
      const status = preparation.get(owner)
      if (status) event.system.push({ type: "text", text: "Project sandbox status: " + JSON.stringify(status) + ". Use poseidon_workspace for settings and tests; orchestration uses native agents, not a controller." })
    })
    await ctx.command.transform((editor) => {
      editor.add({
        name: "poseidon-resources",
        description: "Export redacted resource diagnostics as JSON",
        execute: async ({ sessionID }) => {
          await governor.sample()
          await ctx.session.synthetic({ sessionID, text: JSON.stringify(governor.report()), resume: false })
        },
      })
      editor.add({
        name: "poseidon-logs",
        description: "Show a saved workspace operation: /poseidon-logs LOG_ID",
        execute: async ({ sessionID, prompt }) => {
          const owner = await rootSession(sessionID)
          const result = await governor.execute(logCommand(prompt.text.trim()), {
            sessionID: owner, agentID: "operator", cleanup: true,
            signal: AbortSignal.timeout(30000),
          })
          if (result.code !== 0) throw new Error(result.stderr || "Log read failed")
          await ctx.session.synthetic({ sessionID: owner, text: result.stdout, resume: false })
        },
      })
      editor.add({
        name: "poseidon-end",
        description: "Remove this chat's sandbox while preserving settings and project work",
        execute: async ({ sessionID }) => {
          const owner = await rootSession(sessionID)
          const output = await invoke({ action: "end_sandbox", session_id: owner })
          preparation.delete(owner)
          await ctx.session.synthetic({ sessionID: owner, text: "Session sandbox ended. " + output, resume: false })
        },
      })
    })
    const events = new AbortController()
    const subscription = (async () => {
      for await (const event of ctx.event.subscribe({ types: ["session.archived", "session.deleted"], signal: events.signal })) {
        const sessionID = event.data?.sessionID ?? event.sessionID
        if (!sessionID) continue
        try {
          // Do not resolve child IDs to parents here: deleting a subagent must not
          // terminate the user chat's sandbox.
          governor.cancelSession(sessionID)
          await invoke({ action: "end_sandbox", session_id: sessionID })
          preparation.delete(sessionID)
        } catch (error) { console.error("Session sandbox cleanup failed", error) }
      }
    })().catch((error) => { if (!events.signal.aborted) console.error("Sandbox lifecycle subscription failed", error) })
    await ctx.tool.transform((editor) => editor.add({
      name: "poseidon_workspace",
      description: "Sandbox infrastructure only: read settings/status, configure a Docker image/build recipe and tests, run tests, or end the sandbox. No controller, approval token, rubric phase or model authentication. Returns a runtime path for use through the native shell tool; structured tool calls also forward live progress.",
      options: { permission: "poseidon_workspace", codemode: false },
      input: {
        type: "object",
        properties: {
          action: { type: "string", enum: ["settings", "configure", "test", "status", "end_sandbox"] },
          tests: { type: "object", additionalProperties: true, description: "For configure: image, commands (argv arrays), timeout_seconds." },
          sandbox: { type: "object", additionalProperties: true, description: "For configure: Docker executable/context or host; optional build {dockerfile: Dockerfile text, timeout_seconds}; environment, prepare_commands and resource limits. Omit to reuse persisted settings." },
        },
        required: ["action"], additionalProperties: false,
      },
      execute: async (input, context) => {
        // Check the real calling agent and action before any host-side helper runs.
        // The coarse tool visibility check alone cannot distinguish test/configure.
        await ctx.permission.assert({
          sessionID: context.sessionID,
          agent: context.agent,
          source: { type: "tool", messageID: context.messageID, id: context.id },
          action: "poseidon_workspace",
          resources: [input.action],
          save: [input.action],
        })
        const owner = await rootSession(context.sessionID)
        const output = await invoke({ ...input, session_id: owner }, context.signal,
          typeof context.progress === "function" ? (update) => context.progress(update) : undefined, context.agent)
        const result = JSON.parse(output)
        if (result.sandbox) remember(owner, result.sandbox)
        if (input.action === "end_sandbox") remember(owner, result)
        if (input.action === "status") result.resources = governor.report()
        return { content: JSON.stringify(result) }
      },
    }))
    // Executable transforms replay on MCP refresh. Separate agent/tool lanes avoid
    // a parent subagent holding a tool slot while its shell call waits for one.
    await ctx.tool.transform((editor) => {
      let wrapped = 0, unavailable = 0
      for (const info of editor.list()) {
        if (["poseidon_workspace", "execute"].includes(info.id)) continue // Managed at invoke(), including cleanup exemptions.
        editor.update(info.id, (tool) => {
          const execute = tool.execute
          if (typeof execute !== "function") { unavailable++; return }
          wrapped++
          const kind = info.id === "subagent" ? "agent" : info.id === "shell" ? "shell" : "tool"
          tool.execute = async (input, context) => {
            let depth = 0, sessionID = context.sessionID
            const seen = new Set()
            while (sessionID && !seen.has(sessionID)) {
              seen.add(sessionID)
              const response = await ctx.session.get({ sessionID })
              const session = response.data ?? response
              if (!session.parentID) break
              depth++; sessionID = session.parentID
              if (depth >= governor.config.maxDepth) break
            }
            return governor.run(kind, signal => execute(input, { ...context, signal }), {
              signal: context.signal, sessionID: await rootSession(context.sessionID), agentID: context.agent,
              taskID: context.id, depth,
            })
          }
        })
      }
      governor.event("tool-boundary", { wrapped, unavailable })
    })
    const cleanupReliability = await reliability.setup(ctx, governor)
    return async () => {
      await cleanupReliability()
      events.abort()
      const signal = AbortSignal.timeout(10000)
      // Cleanup has a separate bounded lane, even if heavy work is saturated.
      for (const owner of preparation.keys()) {
        governor.cancelSession(owner)
        try { await invoke({ action: "end_sandbox", session_id: owner }, signal) }
        catch { governor.event("cleanup-warning") }
        if (signal.aborted) break
      }
      await governor.close()
      preparation.clear()
      await subscription
    }
  },
}
