import { test } from "node:test"
import assert from "node:assert/strict"
import plugin from "../.opencode/plugins/poseidon-workspace/index.js"
import { createHash } from "node:crypto"
import { mkdtemp, readFile, rm, access, mkdir, writeFile, readdir } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { execFileSync } from "node:child_process"
import { setTimeout } from "node:timers/promises"

async function fixture(prefix = "poseidon-native-", native = [], git = true) {
  const directory = await mkdtemp(path.join(tmpdir(), prefix))
  if (git) execFileSync("git", ["init", "-q", directory])
  const hooks = new Map(), commands = new Map(), prompts = [], queue = [], synthetic = []
  const tools = new Map(native.map(t => [t.id, { ...t }]))
  let tool, stopped = false
  const stored = new Map()
  const cleanup = await plugin.setup({
    location: { directory },
    storage: { get: async key => structuredClone(stored.get(key)), set: async (key,value) => { stored.set(key,structuredClone(value)) } },
    session: {
      get: async ({ sessionID }) => ({ data: { id: sessionID, agent: "team-lead", ...(sessionID === "child" ? { parentID: "parent" } : {}) } }),
      hook: async (name, handler) => { const previous=hooks.get(name); hooks.set(name, previous ? async event => { await previous(event); await handler(event) } : handler) },
      synthetic: async (value) => { assert.equal(value.resume, false); synthetic.push(value) },
      prompt: async (value) => { prompts.push(value) },
    },
    permission: { assert: async ({ action, resources, agent }) => {
      assert.equal(action, "poseidon_workspace")
      if (agent && !["poseidon", "team-lead"].includes(agent) && !["settings", "status"].includes(resources[0])) {
        throw new Error("Permission denied")
      }
    } },
    command: { transform: async (register) => register({ add: (command) => commands.set(command.name, command) }) },
    tool: { list: async () => [...tools.values()], transform: async (register) => register({
      add: (definition) => { tool = definition; tools.set(definition.name, { ...definition, id: definition.name }) },
      list: () => [...tools.values()],
      update: (id, update) => update(tools.get(id)),
    }) },
    event: { async *subscribe({ signal }) {
      let cursor = 0
      while (!signal.aborted) {
        if (cursor < queue.length) yield queue[cursor++]
        else await setTimeout(10)
      }
      stopped = true
    } },
  })
  const marker = (id) => path.join(directory, git ? ".git/bdfl/sessions" : ".opencode/workspace/sessions", createHash("sha256").update(JSON.stringify(id)).digest("hex").slice(0, 24), "ended")
  const waitForMarker = async (id) => {
    for (let attempt = 0; attempt < 200; attempt++) {
      try { await access(marker(id)); return } catch { await setTimeout(10) }
    }
    assert.fail("Cleanup did not complete: " + id)
  }
  return { directory, hooks, commands, tool: tools.get("poseidon_workspace"), tools, prompts, synthetic, queue, marker, waitForMarker, async cleanup() {
    await cleanup()
    for (let attempt = 0; !stopped && attempt < 50; attempt++) await setTimeout(10)
    await rm(directory, { recursive: true, force: true })
  } }
}

test("workspace tool uses native permissions and root session ownership, without custom authorization or controller submission", async () => {
  const f = await fixture()
  try {
    assert.equal(f.tool.name, "poseidon_workspace")
    assert.equal(f.tool.options.permission, "poseidon_workspace")
    assert.equal(f.tool.options.codemode, false)
    assert.deepEqual(f.tool.input.properties.action.enum, ["settings", "configure", "test", "status", "end_sandbox"])
    const result = await f.tool.execute({ action: "settings" }, { sessionID: "child" })
    const settings = JSON.parse(result.content)
    assert.equal(settings.settings, null)
    assert.ok(settings.tests_template.commands.length)
    const status = JSON.parse((await f.tool.execute({ action: "status" }, { sessionID: "child" })).content)
    assert.equal(status.resources.version, 1)
    assert.equal(status.resources.config.maxAgents, 1)
    assert.equal(status.resources.config.maxTools, 1)
    assert.ok(!JSON.stringify(status.resources).includes("environment"))
    await assert.rejects(access(path.join(f.directory, ".git/bdfl/runs")))
  } finally { await f.cleanup() }
})

test("delegated agents share the user sandbox; deleting a child does not end its parent", async () => {
  const f = await fixture()
  try {
    await f.hooks.get("prompt")({ sessionID: "parent" })
    const operations = path.join(f.directory, ".git/bdfl/operations")
    const count = (await readdir(operations)).length
    await f.hooks.get("prompt")({ sessionID: "child" })
    assert.equal((await readdir(operations)).length, count)
    const context = { sessionID: "child", agent: "team-lead", system: [], options: {}, tools: {} }
    await f.hooks.get("context")(context)
    assert.match(context.system[0].text, /needs_configuration/)
    f.queue.push({ type: "session.deleted", data: { sessionID: "child" } })
    await f.waitForMarker("child")
    await assert.rejects(access(f.marker("parent")))
    f.queue.push({ type: "session.archived", data: { sessionID: "parent" } })
    await f.waitForMarker("parent")
    await f.commands.get("poseidon-end").execute({ sessionID: "child" })
  } finally { await f.cleanup() }
})

test("log command follows native operation output with quoted paths and rejects shell injection", async () => {
  const f = await fixture("poseidon-'logs-")
  try {
    const id = "a".repeat(32)
    const directory = path.join(f.directory, ".git/bdfl/operations", id)
    await mkdir(directory, { recursive: true })
    await writeFile(path.join(directory, "state.json"), JSON.stringify({ finished: true, failed: false }))
    await writeFile(path.join(directory, "output.log"), "NATIVE_LOG_MARKER\n")
    await f.commands.get("poseidon-logs").execute({ sessionID: "child", prompt: { text: id } })
    const viewer = f.synthetic.at(-1)
    assert.equal(viewer.sessionID, "parent")
    assert.match(viewer.text, /NATIVE_LOG_MARKER/)
    assert.equal(f.prompts.length, 0)
    await assert.rejects(f.commands.get("poseidon-logs").execute({ sessionID: "parent", prompt: { text: id + "; echo injected" } }), /Invalid log ID/)
  } finally { await f.cleanup() }
})


test("workspace checks the calling worker before helper execution", async () => {
  const f = await fixture()
  try {
    for (const action of ["configure", "test", "end_sandbox"]) {
      await assert.rejects(f.tool.execute({ action }, { sessionID: "child", agent: "researcher" }), /Permission denied|Top-level agents|Session role changed/)
    }
    for (const agent of ["coder", "reviewer"]) {
      for (const action of ["configure", "end_sandbox"]) {
        await assert.rejects(f.tool.execute({ action }, { sessionID: "child", agent }), /Permission denied|Top-level agents|Session role changed/)
      }
    }
    // Rejection happened before the host helper created settings or operation logs.
    await assert.rejects(access(path.join(f.directory, ".git/bdfl")))
  } finally { await f.cleanup() }
})


test("native tool transforms admit agent and heavy calls without holding a dispatcher slot", async () => {
  let active = 0, peak = 0
  const execute = async (_input, context) => {
    assert.ok(context.signal instanceof AbortSignal)
    active++; peak = Math.max(peak, active)
    await setTimeout(30)
    active--
    return { content: "done" }
  }
  const dispatcher = async () => ({ content: "dispatch" })
  const f = await fixture("poseidon-governed-", [
    {id:"read",execute}, {id:"shell",execute}, {id:"remote_mcp",execute}, {id:"execute",execute:dispatcher},
  ])
  try {
    await Promise.all(Array.from({length:4}, () => f.tools.get("read").execute({path:"a.md"}, {sessionID:"parent", agent:"team-lead"})))
    assert.equal(peak,1)
    for (const id of ["remote_mcp", "execute"]) {
      await assert.rejects(f.tools.get(id).execute({}, {sessionID:"parent",agent:"team-lead"}), /Unclassified tool/)
    }
  } finally { await f.cleanup() }
})
test("an existing global workspace tool is reused without duplicate sandbox hooks",async()=>{
 const original=async()=>({content:'existing'})
 const f=await fixture('workspace-compatible-',[{id:'poseidon_workspace',execute:original}])
 try{
  // The only prompt hook is reliability's bounded-turn reset; it does not provision a sandbox.
  await f.hooks.get('prompt')({sessionID:'parent'})
  await assert.rejects(access(path.join(f.directory,'.git/bdfl/operations')))
  assert.ok(f.tools.has('agent_contracts'));assert.ok(f.commands.has('confirm-brief'))
 }finally{await f.cleanup()}
})

test("ordinary-folder prompt preparation and log viewing use local workspace state", async () => {
  const f = await fixture("poseidon-non-git-", [], false)
  try {
    await f.hooks.get("prompt")({ sessionID: "parent" })
    const settings = JSON.parse((await f.tool.execute({action:"settings"}, {sessionID:"child"})).content)
    assert.equal(settings.settings, null)
    assert.equal(settings.settings_file, path.join(f.directory,".opencode/workspace/settings.json"))
    const operations = await readdir(path.join(f.directory,".opencode/workspace/operations"))
    assert.equal(operations.length, 1)
    await f.commands.get("poseidon-logs").execute({sessionID:"parent",prompt:{text:operations[0]}})
    assert.match(f.synthetic.at(-1).text, /operation completed/)
    await f.commands.get("poseidon-end").execute({sessionID:"parent"})
    await access(f.marker("parent"))
    await assert.rejects(access(path.join(f.directory,".git")))
  } finally { await f.cleanup() }
})

test("all workers can read sandbox metadata but cannot mutate a Docker target",async()=>{
 const f=await fixture()
 try{
  for(const role of ['researcher','maintainer','coder','reviewer']){
   const result=JSON.parse((await f.tool.execute({action:'settings'},{sessionID:role,agent:role})).content)
   assert.equal(result.settings,null)
   for(const action of ['configure','test','end_sandbox'])await assert.rejects(f.tool.execute({action},{sessionID:role,agent:role}),/Top-level agents/)
  }
 }finally{await f.cleanup()}
})
