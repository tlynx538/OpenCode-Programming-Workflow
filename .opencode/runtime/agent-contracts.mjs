/** Trusted, deterministic contracts. Evidence validation is structural, not semantic entailment. */
import { createHash } from 'node:crypto'
import { realpath } from 'node:fs/promises'
import path from 'node:path'
import { homedir } from 'node:os'
export const roles = ['poseidon', 'team-lead', 'researcher', 'maintainer', 'coder', 'reviewer']
export const types = ['VERIFIED_FACT', 'DOCUMENTED_STANDARD', 'OBSERVED_CONVENTION', 'DESIGN_HYPOTHESIS', 'SUBJECTIVE_OPINION', 'UNSUPPORTED', 'UNKNOWN']
export const words = text => String(text).trim().split(/\s+/u).filter(Boolean).length
export const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex')
export const need = (ok, message) => { if (!ok) throw Error(message) }
const text = (s, name) => need(typeof s === 'string' && s.trim().length > 0 && s.length <= 16000, 'Invalid ' + name)
const list = (xs, name) => { need(Array.isArray(xs) && xs.length <= 64, 'Invalid ' + name); xs.forEach(s => text(s, name)) }
export function safeRelative(s) {
  text(s, 'scope path')
  need(s === '.' || (!path.isAbsolute(s) && !s.includes('\\') && !s.split('/').some(p => ['', '.', '..'].includes(p)) && !/[\x00-\x1f:*?]/.test(s)), 'Unsafe scope path')
  need(!s.split('/').some(p => ['.git', '.opencode', '.agents', '.codex', '.ssh', '.aws', '.gnupg'].includes(p)) && !/(^|\/)(\.env(?:\..*)?|.*\.(pem|key)|.*credentials.*|auth\.json)$/i.test(s), 'Protected scope path')
  return s
}
export function assignment(value, limits) {
  need(value && typeof value === 'object', 'Assignment required')
  const t = structuredClone(value)
  need(Object.keys(t).every(k=>['id','to','objective','question','purpose','scope','exclusions','sourceTypes','skills','acceptance','nextAction','design','budget','briefID','briefVersion','reviewOf','researchTaskID','from','status'].includes(k)), 'Unknown assignment field')
  text(t.id, 'task id'); need(/^[a-zA-Z0-9_-]{1,64}$/.test(t.id), 'Unsafe task id')
  need(roles.includes(t.to) && t.to !== 'poseidon', 'Unknown subordinate')
  for (const k of ['objective', 'question', 'purpose', 'nextAction']) text(t[k], k)
  for (const k of ['scope', 'exclusions', 'sourceTypes', 'skills', 'acceptance']) list(t[k], k)
  need(t.scope.length && t.acceptance.length, 'Scope and acceptance required')
  t.scope.forEach(safeRelative); t.exclusions.forEach(safeRelative)
  need(t.sourceTypes.every(x => ['local','web','mcp','system'].includes(x)), 'Unknown source type')
  t.budget = { ...limits, ...(t.budget ?? {}) }
  for (const [k,v] of Object.entries(t.budget)) {
    need(k in limits && Number.isInteger(v) && v > 0, 'Invalid budget: ' + k)
    t.budget[k]=Math.min(v,limits[k])
  }
  need(t.to !== 'researcher' || t.skills.every(s => s === 'karpathy-guidelines'), 'Unauthorized research skill')
  need(typeof t.design === 'boolean', 'Explicit design classification required')
  if (t.design && t.to === 'coder') { text(t.briefID, 'brief id'); need(Number.isInteger(t.briefVersion), 'Brief version required') }
  return { ...t, from: 'poseidon', status: 'ASSIGNED' }
}
export function validateBrief(b, previous) {
  need(b && typeof b === 'object', 'Brief required')
  b={...structuredClone(b),reason:b.reason??b['reason-for-revision']??b.reasonForRevision}
  delete b['reason-for-revision'];delete b.reasonForRevision
  if(b.reason===undefined)delete b.reason
  text(b.id, 'brief id')
  need(/^[\w-]{1,64}$/.test(b.id), 'Unsafe brief id')
  need(b.version === (previous?.version ?? 0) + 1, 'Brief revision must advance once')
  for (const k of ['goals','preferences','prohibitions','functional','technical','accessibility','acceptance','openQuestions']) list(b[k], k)
  need(b.goals.length && b.acceptance.length, 'Goals and acceptance required')
  need(Array.isArray(b.decisions) && b.decisions.length <= 64, 'Decisions required')
  for (const d of b.decisions) {
    text(d.id,'decision id'); text(d.text,'decision text'); text(d.provenance,'decision provenance')
    need(['USER_STATEMENT','ASSUMPTION','SUGGESTION'].includes(d.kind), 'Unknown decision kind')
  }
  need(new Set(b.decisions.map(d => d.id)).size === b.decisions.length, 'Duplicate decision id')
  if (previous) {
    text(b.reason, 'revision reason')
    for (const field of ['goals','preferences','prohibitions','functional','technical','accessibility','acceptance']) {
      for (const value of previous[field]) if (!b[field].includes(value)) {
        const change=(b.changes??[]).find(c=>c.field===field&&c.previous===value)
        need(change, 'Removed requirement needs explicit change provenance: '+field)
        text(change.reason,'change reason');text(change.provenance,'change provenance')
      }
    }
    for(const decision of previous.decisions)if(!b.decisions.some(d=>d.id===decision.id&&d.text===decision.text)){
      const change=(b.changes??[]).find(c=>c.field==='decisions'&&c.previous===decision.id)
      need(change,'Changed decision needs explicit provenance');text(change.reason,'change reason');text(change.provenance,'change provenance')
    }
  }
  return { ...structuredClone(b), confirmed: false, previousHash: previous ? digest(previous) : null }
}
export function briefHash(brief) {
  const value=structuredClone(brief);value.confirmed=false
  for(const key of ['confirmedBy','confirmedAt'])delete value[key]
  return digest(value)
}

export function handoff(h, task, state, limit) {
  if(typeof h==='string')h={summary:h}
  if(h&&typeof h==='object'&&Object.keys(h).length===1&&'handoff'in h){h=h.handoff;if(typeof h==='string'){try{h=JSON.parse(h)}catch{h={summary:h}}}}
  need(h && typeof h === 'object', 'Handoff required')
  const provided=structuredClone(h)
  text(provided.summary,'summary')
  h={...handoffTemplate(task),...provided}
  need(Buffer.byteLength(JSON.stringify(h))<=65536,'Handoff exceeds the 64 KiB storage limit; submit a focused report')
  const warnings=[]

  need(Object.keys(h).every(k=>['taskID','from','to','objective','scope','exclusions','briefVersion','status','summary','claims','verification','uncertainty','nextAction','verdict','findings'].includes(k)), 'Unknown handoff field')
  for (const k of ['taskID','from','to','objective','summary','nextAction']) text(h[k], k)
  need(h.taskID === task.id && h.from === task.to && h.to === 'poseidon', 'Unauthorized handoff routing')
  need(h.objective === task.objective, 'Objective changed')
  need(JSON.stringify(h.scope) === JSON.stringify(task.scope) && JSON.stringify(h.exclusions) === JSON.stringify(task.exclusions), 'Scope changed')
  need(h.briefVersion === (task.briefVersion ?? null), 'Brief version changed')
  list(h.uncertainty,'uncertainty'); list(h.verification,'verification')
  need(['COMPLETE','PARTIAL','INSUFFICIENT'].includes(h.status), 'Unknown handoff status')
  if(words([h.summary,h.nextAction,...h.uncertainty,...h.verification,...(h.claims??[]).map(c=>c.text)].join(' '))>limit)warnings.push('Long report preserved; prefer a concise summary next time')
  need(Array.isArray(h.claims) && h.claims.length <= 32, 'Claims required')
  const sources = new Map(state.sources.map(s => [s.id,s]))
  for (const [index,c] of h.claims.entries()) {
    c.id??='C'+(index+1);c.type??='UNKNOWN';c.sourceIDs??=[]
    text(c.id,'claim id');text(c.text,'claim text');need(types.includes(c.type),'Unknown claim classification');list(c.sourceIDs,'source IDs')
    need(c.sourceIDs.every(id => sources.has(id)), 'Claim cites an unretrieved source')
    if (['VERIFIED_FACT','DOCUMENTED_STANDARD','OBSERVED_CONVENTION'].includes(c.type)) {
      const matched=c.sourceIDs.length&&typeof c.quote==='string'&&c.quote.trim()&&c.sourceIDs.some(id=>sources.get(id).excerpt.includes(c.quote))
      c.evidenceStatus=matched?'QUOTE_MATCH_REVIEW_REQUIRED':'UNVERIFIED_REVIEW_REQUIRED'
      if(!matched){c.requestedType=c.type;c.type='UNKNOWN';warnings.push('Claim '+c.id+': quotation not verified; retained for independent review')}
    }
  }
  need(new Set(h.claims.map(c=>c.id)).size === h.claims.length, 'Duplicate claim id')
  if(warnings.length)h.warnings=warnings
  h.sourceIDs=state.sources.map(s=>s.id)
  if (h.from === 'reviewer') {
    need(['PASS','PASS_WITH_WARNINGS','FAIL','INCONCLUSIVE'].includes(h.verdict),'Reviewer verdict required')
    need(Array.isArray(h.findings), 'Review findings required')
    for (const f of h.findings) {
      for(const k of ['location','problem','evidence','impact','confidence','remediation']) text(f[k], k)
      need(['P0','P1','P2','P3','PREFERENCE'].includes(f.severity),'Invalid severity')
      if (f.severity === 'P0') text(f.immediateDanger,'P0 immediate danger')
    }
    need(h.verdict !== 'PASS' || h.findings.length === 0,'PASS conflicts with findings')
    need(h.verdict !== 'FAIL' || h.findings.some(f => f.severity !== 'PREFERENCE'),'Preferences cannot alone fail review')
  }
  return structuredClone(h)
}
export function fallback(task, state, reason) {
  return {taskID:task.id,from:task.to,to:'poseidon',objective:task.objective,scope:task.scope,exclusions:task.exclusions,
    briefVersion:task.briefVersion??null,status:'PARTIAL',summary:'Execution ended without an accepted handoff. Collected sources require review.',
    claims:[],sourceIDs:state.sources.map(s=>s.id),verification:[],uncertainty:[reason],nextAction:'Review collected evidence and explicitly reassign remaining work.',
    ...(task.to === 'reviewer' ? {verdict:'INCONCLUSIVE',findings:[]} : {})}
}
export function spend(state, kind, limits, now) {
  need(now - state.started < limits.seconds * 1000,'Runtime budget exhausted')
  need(state.calls < limits.tools,'Tool budget exhausted')
  if(kind === 'websearch') need((state.searches??0) < (limits.searches??3),'Search budget exhausted')
  if(kind === 'webfetch') need((state.pages??0) < (limits.pages??4),'Page budget exhausted')
  state.calls++
  if(kind==='websearch') state.searches=(state.searches??0)+1
  if(kind==='webfetch') state.pages=(state.pages??0)+1
}
export function hostControlPath(target, home=homedir()) {
  return ['.ssh','.aws','.gnupg','.config/opencode','.codex','.agents','.local/share/opencode','.local/state/opencode'].some(name=>{
    const base=path.join(home,name)
    return target===base||target.startsWith(base+path.sep)
  })
}
export async function scopedPath(root, candidate, task, write=false) {
  text(candidate,'tool path')
  const absolute=path.resolve(root,candidate);let ancestor=absolute;const tail=[]
  while(true) { try { ancestor=await realpath(ancestor);break } catch(e) { if(e.code!=='ENOENT')throw e;const up=path.dirname(ancestor);need(up!==ancestor,'Cannot resolve path');tail.unshift(path.basename(ancestor));ancestor=up } }
  const canonicalRoot=await realpath(root)
  need(!hostControlPath(path.join(ancestor,...tail)),'Protected host credentials or agent control storage')
  need(ancestor===canonicalRoot || ancestor.startsWith(canonicalRoot+path.sep),'Path escapes project or follows external symlink')
  const rel=path.relative(canonicalRoot,path.join(ancestor,...tail)).split(path.sep).join('/') || '.';safeRelative(rel)
  const includes = (p,x) => p==='.' || x===p || x.startsWith(p+'/')
  need(task.scope.some(p=>includes(p,rel)) && !task.exclusions.some(p=>includes(p,rel)), 'Path outside task scope')
  if(write) need(roles.includes(task.to),'Only known agents edit assigned local development source')
  return absolute
}
export function editPaths(input) {
  const patch=input.patchText??input.patch
  if(typeof patch==='string') {
    const files=[...patch.matchAll(/^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$/gm)].map(m=>m[1])
    need(files.length,'Unrecognized patch format');return files
  }
  const p=input.path??input.filePath??input.file_path
  need(typeof p==='string','Unknown write tool path; denied');return [p]
}

/** Literal, bounded local search; never follows symlinks or searches protected paths. */
export async function searchProject(root, task, query, signal) {
  const { opendir, readFile, stat } = await import('node:fs/promises')
  need(typeof query==='string'&&query.length>0&&query.length<=256,'Bounded literal query required')
  const queue=[...task.scope],matches=[];let visited=0,files=0,truncated=false
  while(queue.length&&visited<512&&files<200&&matches.length<40){
    signal?.throwIfAborted();const rel=queue.shift();visited++
    if(rel!=='.')try{safeRelative(rel)}catch{continue}
    if(task.exclusions.some(p=>rel===p||rel.startsWith(p+'/')))continue
    if(rel!=='.')try{await scopedPath(root,rel,task)}catch{continue}
    const absolute=path.join(root,rel)
    const st=await stat(absolute).catch(()=>null);if(!st)continue
    if(st.isDirectory()){
      const dir=await opendir(absolute)
      for await(const e of dir){
        if(e.isSymbolicLink()||['node_modules','dist','build','coverage','__pycache__'].includes(e.name))continue
        const next=rel==='.'?e.name:rel+'/'+e.name
        try{safeRelative(next)}catch{continue}
        if(queue.length<512)queue.push(next);else truncated=true
      }
    }else if(st.isFile()&&st.size<=65536&&/\.(?:md|txt|html|css|json|py|[cm]?js|tsx?|jsx|ya?ml|toml)$/.test(rel)){
      await scopedPath(root,rel,task);files++
      const lines=(await readFile(absolute,'utf8')).split('\n')
      for(let i=0;i<lines.length&&matches.length<40;i++)if(lines[i].includes(query))matches.push({path:rel,line:i+1,text:lines[i].slice(0,1000)})
    }
  }
  return {matches,filesInspected:files,partial:truncated||queue.length>0,coverage:'Bounded local search; absence of matches does not establish absence.'}
}

/** Bounded filename discovery inside assigned paths; never follows symlinks. */
export async function discoverProject(root, task, input, signal) {
  const { opendir, lstat } = await import('node:fs/promises')
  const pattern=input.pattern
  need(typeof pattern==='string'&&pattern.length>0&&pattern.length<=256&&!/[\\\x00-\x1f{}[\]]/.test(pattern),'Use a bounded glob with *, ** or ?')
  need(!path.isAbsolute(pattern)&&!pattern.split('/').some(p=>p==='..'||p==='.'),'Glob pattern must stay relative to its search directory')
  const base=path.resolve(root,input.path??'.'),canonicalRoot=await realpath(root)
  const relativeBase=path.relative(canonicalRoot,base).split(path.sep).join('/')||'.'
  safeRelative(relativeBase)
  const contains=(a,b)=>a==='.'||a===b||b.startsWith(a+'/')
  const queue=task.scope.filter(p=>contains(relativeBase,p)||contains(p,relativeBase)).map(p=>contains(p,relativeBase)?relativeBase:p)
  need(queue.length,'Search directory is outside task scope')
  let regex=''
  for(let i=0;i<pattern.length;i++){
    const c=pattern[i]
    if(c==='*'&&pattern[i+1]==='*') { i++;if(pattern[i+1]==='/'){i++;regex+='(?:.*/)?'}else regex+='.*' }
    else regex+=c==='*'?'[^/]*':c==='?'?'[^/]':c.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')
  }
  const matcher=new RegExp('^'+regex+'$'),files=[],seen=new Set()
  const limit=Math.min(Number.isInteger(input.limit)&&input.limit>0?input.limit:100,200)
  let visited=0,entries=0,truncated=false
  while(queue.length&&visited<512&&files.length<limit){
    signal?.throwIfAborted();const rel=queue.shift();if(seen.has(rel))continue;seen.add(rel);visited++
    if(rel!=='.')try{safeRelative(rel)}catch{continue}
    if(task.exclusions.some(p=>contains(p,rel)))continue
    if(rel!=='.')try{await scopedPath(canonicalRoot,rel,task)}catch{continue}
    const absolute=path.join(canonicalRoot,rel),st=await lstat(absolute).catch(e=>{if(e.code==='ENOENT')return null;throw e})
    if(!st||st.isSymbolicLink())continue
    if(st.isDirectory()){
      const directory=await opendir(absolute)
      for await(const entry of directory){
        if(++entries>4096){truncated=true;break}
        if(entry.isSymbolicLink()||['node_modules','dist','build','coverage','__pycache__'].includes(entry.name))continue
        const next=rel==='.'?entry.name:rel+'/'+entry.name
        try{safeRelative(next)}catch{continue}
        if(queue.length<512)queue.push(next);else truncated=true
      }
    }else if(st.isFile()&&matcher.test(path.relative(base,absolute).split(path.sep).join('/')))files.push(rel)
  }
  return {files,partial:truncated||queue.length>0,coverage:'Bounded filename discovery within assigned scope.'}
}

export function handoffTemplate(task) {
  return {taskID:task.id,from:task.to,to:'poseidon',objective:task.objective,scope:task.scope,
    exclusions:task.exclusions,briefVersion:task.briefVersion??null,status:'PARTIAL',
    summary:'Replace with observed findings.',claims:[],verification:[],uncertainty:[],
    nextAction:'Coordinator reviews findings and assigns remaining work.',
    ...(task.to==='reviewer'?{verdict:'INCONCLUSIVE',findings:[]}: {})}
}
