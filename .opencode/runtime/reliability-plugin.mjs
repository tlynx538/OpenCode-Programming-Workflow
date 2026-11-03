import { reserveNvidia } from './provider-budget.mjs'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { readFileSync } from 'node:fs'
import { realpath, mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { createHash } from 'node:crypto'
import { assignment, validateBrief, handoff, fallback, spend, scopedPath, editPaths, searchProject, discoverProject, handoffTemplate, roles, need, digest, briefHash } from './agent-contracts.mjs'
const matrix = JSON.parse(readFileSync(new URL('../skills/SOURCES.json', import.meta.url))).agents
const limits = JSON.parse(readFileSync(new URL('./agent-limits.json', import.meta.url)))
const readTools = new Set(['read','glob','grep','webfetch','websearch','skill','opencode_list_mcp_resources','opencode_read_mcp_resource'])
const writes = new Set(['edit','write','patch','apply_patch'])
const native = new Set([...readTools,...writes,'question','subagent','agent_contracts','project_search','poseidon_workspace','system_access','shell'])
const unwrap = r => r?.data ?? r
const runFile = promisify(execFile)
const sourceText = r => Array.isArray(r?.content) ? r.content.filter(x=>x.type==='text').map(x=>x.text).join('\n') : typeof r?.content === 'string' ? r.content : JSON.stringify(r?.content ?? r)

export default {
 id:'agent-reliability',
 async setup(ctx,governor) {
  const locks=new Map(), timers=new Map(), audit=new Map()
  const rootOf=async id=>{const seen=new Set();while(id&&!seen.has(id)&&seen.size<16){seen.add(id);const s=unwrap(await ctx.session.get({sessionID:id}));if(!s.parentID)return id;id=s.parentID}throw Error('Invalid session ancestry')}
  const transact=async(root,fn)=>{
   const prior=locks.get(root)??Promise.resolve();const next=prior.catch(()=>{}).then(async()=>{
    const key='root/'+root;const d=await ctx.storage.get(key)??{tasks:{},briefs:{},sessions:{},events:[]};const before=structuredClone(d)
    let result
    try{result=await fn(d)}catch(error){
     // Roll back task/brief mutations, while failed admitted calls still consume budget.
     for(const [id,s]of Object.entries(d.sessions)){
      before.sessions[id]??={role:s.role,taskID:s.taskID,started:s.started,calls:0,searches:0,pages:0,denied:0,modelSteps:0,sources:[],closed:false}
      for(const k of ['calls','searches','pages','denied','modelSteps'])before.sessions[id][k]=Math.max(before.sessions[id][k]??0,s[k]??0)
     }
     await ctx.storage.set(key,before);throw error
    }
    d.events=d.events.slice(-128);await ctx.storage.set(key,d);return result
   });locks.set(root,next);try{return await next}finally{if(locks.get(root)===next)locks.delete(root)}
  }
  const getState=(d,id,role)=>{
   need(roles.includes(role),'Unknown agent')
   if(!d.sessions[id]) {
    need(Object.keys(d.sessions).length<64,'Session record limit reached; start a new root task')
    const t=Object.values(d.tasks).find(t=>t.to===role&&t.status==='RUNNING')
    d.sessions[id]={role,taskID:t?.id??null,started:Date.now(),calls:0,searches:0,pages:0,sources:[],denied:0,modelSteps:0,closed:false}
   }
   need(d.sessions[id].role===role,'Session role changed; use a new session');return d.sessions[id]
  }
  const taskFor=(d,s)=>d.tasks[s.taskID]??{id:'direct-'+s.role,from:'poseidon',to:s.role,objective:'Direct bounded investigation',question:'Answer the current user request',purpose:'Direct session',scope:['.'],exclusions:[],sourceTypes:['local','web','system'],skills:matrix[s.role],acceptance:['Return evidence within scope'],design:false,budget:limits.roles[s.role]}
  const stopTimer=id=>{clearTimeout(timers.get(id));timers.delete(id)}
  const arm=(root,id,s,t)=>{
   if(timers.has(id)||s.closed)return
   const timer=setTimeout(async()=>{
    timers.delete(id)
    try {await transact(root,d=>{const state=d.sessions[id];if(!state||state.closed)return;state.closed=true;state.reason='Runtime budget exhausted';const task=taskFor(d,state);if(d.tasks[task.id]){d.tasks[task.id].handoff=fallback(task,state,state.reason);d.tasks[task.id].status='PARTIAL'}});await ctx.session.interrupt({sessionID:id,resume:false})}catch{}
   },Math.max(1,t.budget.seconds*1000-(Date.now()-s.started)));timer.unref?.();timers.set(id,timer)
  }
  const execute=async(input,context)=>{
   const root=await rootOf(context.sessionID),role=context.agent??unwrap(await ctx.session.get({sessionID:context.sessionID})).agent
   return transact(root,async d=>{
    const s=getState(d,context.sessionID,role),task=taskFor(d,s)
    if(['help','brief','evidence'].includes(input.action)){
     if(input.action==='help')return {submit:{action:'submit',value:{summary:'Observed findings',status:'PARTIAL',claims:[],verification:[],uncertainty:[]}},briefRevision:{action:'propose_brief',value:'Full prior brief with version incremented, reason explaining changes, changes with provenance for removed requirements. reason-for-revision and reasonForRevision also accepted.'},guidance:'Routing is filled automatically. Ordinary final reports are retained as unreviewed PARTIAL handoffs. Word counts are advisory. Source IDs must refer to retrieved evidence; unmatched factual quotations are marked UNKNOWN for review. Use brief to inspect a proposal, evidence to inspect your source ledger or an assigned review target. Protected host control files remain inaccessible.'}
     if(input.action==='brief'){const history=d.briefs[input.value?.id];need(history?.length,'Unknown brief');const brief=history.find(b=>b.version===(input.value.version??history.at(-1).version));need(brief,'Unknown brief version');return brief}
     const owner=task.reviewOf?Object.values(d.sessions).find(x=>x.taskID===task.reviewOf):s
     return {sources:owner?.sources??d.tasks[task.reviewOf]?.handoff?.sources??[]}
    }
    if(s.calls>=task.budget.tools-1)need(input.action==='submit','Final tool slot is reserved for submit')
    spend(s,'agent_contracts',task.budget,Date.now())
    if(input.action==='status')return {task,state:{...s,sources:s.sources.map(({excerpt,...source})=>source)},submitTemplate:handoffTemplate(task),allowedActions:role==='poseidon'?['help','brief','evidence','status','assign','propose_brief','submit']:role==='reviewer'&&task.reviewOf?['help','brief','evidence','status','submit','critique']:['help','brief','evidence','status','submit'],briefs:Object.fromEntries(Object.entries(d.briefs).map(([id,history])=>[id,history.map(b=>({id:b.id,version:b.version,confirmed:b.confirmed,openQuestions:b.openQuestions,hash:briefHash(b)}))])),tasks:role==='poseidon'?Object.fromEntries(Object.entries(d.tasks).map(([id,t])=>[id,{id,to:t.to,status:t.status,summary:t.handoff?.summary}])):undefined,reviewTarget:task.reviewOf?d.tasks[task.reviewOf]?.handoff:undefined}
    if(input.action==='assign') {
     need(role==='poseidon','Only Poseidon assigns work');need(Object.keys(d.tasks).length<128,'Task record limit reached')
     const t=assignment(input.value,limits.roles[input.value?.to]);need(!d.tasks[t.id],'Task ID already exists')
     need(!Object.values(d.tasks).some(x=>x.to===t.to&&['ASSIGNED','RUNNING'].includes(x.status)),'Recipient already owns active work')
     if(t.design&&(t.to==='coder'||t.briefID)){const b=d.briefs[t.briefID]?.find(x=>x.version===t.briefVersion);need(b?.confirmed,'User-confirmed brief required');t.briefHash=briefHash(b)}
     if(t.researchTaskID){const r=d.tasks[t.researchTaskID];need(r?.critique?.verdict==='PASS','Material research needs independent critique')}
     if(t.to==='coder')need(!Object.values(d.tasks).some(x=>x.to==='coder'&&['ASSIGNED','RUNNING'].includes(x.status)),'One implementation owner at a time')
     d.tasks[t.id]=t;d.events.push({type:'assigned',taskID:t.id,to:t.to});return t
    }
    if(input.action==='propose_brief') {
     need(role==='poseidon','Only Poseidon proposes design briefs; workers submit findings with action submit and value {summary,...}');const history=d.briefs[input.value?.id]??[];need(history.length<32,'Brief revision limit reached')
     const b=validateBrief(input.value,history.at(-1));history.push(b);d.briefs[b.id]=history
     const state=await runFile('python3',[fileURLToPath(new URL('./workspace.py',import.meta.url)),'--repo',ctx.location.directory,'state-home'],{timeout:30000,maxBuffer:65536});const directory=path.join(JSON.parse(state.stdout).directory,'briefs');await mkdir(directory,{recursive:true});const file=path.join(directory,`${b.id}-v${b.version}.md`);await writeFile(file,'# '+b.id+' — version '+b.version+'\n\n'+Object.entries(b).map(([key,value])=>'## '+key+'\n\n'+(Array.isArray(value)?value.map(x=>'- '+(typeof x==='string'?x:JSON.stringify(x))).join('\n'):JSON.stringify(value))).join('\n\n')+'\n');
     return {brief:b,file,hash:briefHash(b),confirmationCommand:`/confirm-brief ${b.id} ${b.version} ${briefHash(b)}`,guidance:'Show the proposal and file path to the user before requesting confirmation. Only actual unanswered user decisions belong in openQuestions; verification work belongs in acceptance or technical requirements.'}
    }
    if(input.action==='submit') {
     need(!s.closed,'Task is closed');let h
     try{h=handoff(input.value,task,s,task.budget.words)}catch(error){throw Error(error.message+'. Submit value {summary, status?, claims?, verification?, uncertainty?, nextAction?}; routing is filled automatically. Use help or evidence for the public contract and sources.')}
     if(d.tasks[task.id]){d.tasks[task.id].handoff={...h,sources:s.sources};d.tasks[task.id].status=h.status}
     s.closed=true;s.modelHandoff=true;s.handoff={...h,sources:s.sources};stopTimer(context.sessionID);return s.handoff
    }
    if(input.action==='critique') {
     need(role==='reviewer'&&task.reviewOf===input.value?.taskID,'Only assigned independent Reviewer critiques research')
     const t=d.tasks[input.value.taskID];need(t?.handoff?.from==='researcher','Research handoff missing')
     need(['PASS','FAIL','INCONCLUSIVE'].includes(input.value.verdict),'Critique verdict required')
     need(Array.isArray(input.value.checkedClaims)&&t.handoff.claims.every(c=>input.value.checkedClaims.includes(c.id)),'Every claim must be checked')
     need(typeof input.value.summary==='string'&&input.value.summary.length<=4000,'Bounded critique required')
     t.critique=structuredClone(input.value);return t.critique
    }
    throw Error('Unknown contract action')
   })
  }
  await ctx.tool.transform(editor=>editor.add({name:'agent_contracts',description:'Trusted task assignments and simple reports. help explains contracts; status shows counters; brief(value={id,version?}) retrieves a proposal; evidence retrieves your source excerpts or assigned review target. submit(value={summary,status?,claims?,verification?,uncertainty?,nextAction?}) automatically fills routing. Only Poseidon assigns/proposes briefs. Reviewer critique remains independent. No action confirms a brief.',options:{permission:'agent_contracts',codemode:false},input:{type:'object',properties:{action:{type:'string',enum:['help','brief','evidence','status','assign','propose_brief','submit','critique']},value:{anyOf:[{type:'object',additionalProperties:true},{type:'string'}]}},required:['action'],additionalProperties:false},execute:async(input,c)=>({content:JSON.stringify(await execute(input,c))})}))
  await ctx.tool.transform(editor=>editor.add({name:'project_search',description:'Bounded literal search of assigned local source paths. Does not follow symlinks or search protected files.',options:{permission:'project_search',codemode:false},input:{type:'object',properties:{query:{type:'string'}},required:['query'],additionalProperties:false},execute:async(input,c)=>{const root=await rootOf(c.sessionID);const task=await transact(root,d=>taskFor(d,getState(d,c.sessionID,c.agent)));return {content:JSON.stringify(await searchProject(ctx.location.directory,task,input.query,c.signal))}}}))
  const systemInvoke=async(input,c)=>{
    need(c._trustedTask,'Trusted system-access assignment missing')
    const payload={...input,_scope:c._trustedTask.scope,_exclusions:c._trustedTask.exclusions}
    const invoke=signal=>new Promise((resolve,reject)=>{
     const child=execFile('python3',[fileURLToPath(new URL('./system-access.py',import.meta.url)),'--repo',ctx.location.directory,'--agent',c.agent],{signal,timeout:Math.min(330000,(input.timeout_seconds??60)*1000+40000),maxBuffer:1024*1024},(error,stdout,stderr)=>{
      let value;try{value=JSON.parse(stdout)}catch{reject(Error(error?.message??'Invalid system access result'));return}
      if(error||value.error)reject(Error(value.error??error.message));else resolve(value)
     });child.stdin.on('error',()=>{});child.stdin.end(JSON.stringify(payload))
    });const result=governor?await governor.run(input.action==='local_command'?'shell':'tool',invoke,{signal:c.signal,sessionID:await rootOf(c.sessionID),agentID:c.agent,taskID:c.id}):await invoke(c.signal)
    const {output,stderr,...metadata}=result
    return {content:JSON.stringify(metadata)+(typeof output==='string'?'\n'+output:'')+(stderr?'\nSTDERR:\n'+stderr:'')}
  }
  await ctx.tool.transform(editor=>editor.add({
   name:'system_access',description:'Role-aware infrastructure access. connections lists configured profiles. server.*, postgres.*, mysql.*, rabbitmq.* and jenkins.* are fixed REMOTE READ-ONLY observations, never arbitrary SQL, remote commands, publishing, consuming or deployments. local_command runs a scoped local development command with no host network, HOME, SSH keys or credential environment. local_http writes only to explicitly configured development-only loopback services. Poseidon and Team Lead use native shell for full authorized remote administration.',
   options:{permission:'system_access',codemode:false},
   input:{type:'object',properties:{action:{type:'string',enum:['connections','public_fetch','server.status','server.processes','server.containers','server.service','server.logs','postgres.tables','postgres.columns','postgres.rows','mysql.tables','mysql.columns','mysql.rows','rabbitmq.status','rabbitmq.queues','rabbitmq.exchanges','rabbitmq.bindings','rabbitmq.vhosts','jenkins.jobs','jenkins.config','jenkins.build','jenkins.log','local_command','local_http']},profile:{type:'string'},url:{type:'string'},service:{type:'string'},schema:{type:'string'},table:{type:'string'},columns:{type:'array',items:{type:'string'}},filters:{type:'object',additionalProperties:true},limit:{type:'integer'},job:{type:'string'},build:{type:'integer'},command:{type:'string'},timeout_seconds:{type:'integer'},path:{type:'string'},method:{type:'string',enum:['GET','POST','PUT','PATCH','DELETE']},body:{type:'object',additionalProperties:true}},required:['action'],additionalProperties:false},
   execute:systemInvoke
  }))
  await ctx.command.transform(editor=>{
   editor.add({name:'confirm-brief',description:'Confirm an inspected proposal: ID VERSION HASH. This operator command is never an agent tool.',execute:async({sessionID,prompt})=>{
    const [id,version,hash,...extra]=prompt.text.trim().split(/\s+/);need(!extra.length,'Expected ID VERSION HASH');const root=await rootOf(sessionID)
    const result=await transact(root,d=>{const b=d.briefs[id]?.at(-1);need(b&&b.version===Number(version)&&(briefHash(b)===hash||digest(b)===hash),'Stale or changed brief proposal');need(!b.openQuestions.length,'Resolve open questions before confirmation');if(!b.confirmed){b.confirmed=true;b.confirmedBy='USER_COMMAND';b.confirmedAt=new Date().toISOString()};return b})
    await ctx.session.synthetic({sessionID,text:JSON.stringify(result),resume:false})
   }})
   editor.add({name:'agent-audit',description:'Inspect registered tools and bounded session telemetry, without provider secrets.',execute:async({sessionID})=>{
    await ctx.tool.list?.()
    const root=await rootOf(sessionID);const data=await transact(root,d=>({toolAudit:[...audit.values()],sessions:Object.fromEntries(Object.entries(d.sessions).map(([id,s])=>[id,{role:s.role,calls:s.calls,denied:s.denied,searches:s.searches,pages:s.pages,closed:s.closed}]))}))
    console.info('agent-reliability-tool-audit',JSON.stringify(data.toolAudit))
    await ctx.session.synthetic({sessionID,text:JSON.stringify(data),resume:false})
   }})
   editor.add({name:'agent-export',description:'Operator-only export of bounded evaluation evidence into workspace-local storage.',execute:async({sessionID})=>{
    const root=await rootOf(sessionID);const record=await transact(root,d=>{const s=d.sessions[sessionID];need(s,'No execution evidence');const t=taskFor(d,s);const accepted=s.handoff??d.tasks[t.id]?.handoff;
     const h=accepted??fallback(t,s,'No accepted model handoff before completion');s.closed=true;stopTimer(sessionID);return {sessionID,task:t,state:s,handoff:h,modelHandoff:Boolean(s.modelHandoff),fallback:!s.modelHandoff}
    });const result=await runFile('python3',[fileURLToPath(new URL('./workspace.py',import.meta.url)),'--repo',ctx.location.directory,'state-home'],{timeout:30000,maxBuffer:65536});const directory=path.join(JSON.parse(result.stdout).directory,'agent-evals');await mkdir(directory,{recursive:true});await writeFile(path.join(directory,digest(sessionID)+'.json'),JSON.stringify(record,null,2));await ctx.session.synthetic({sessionID,text:'Evaluation evidence exported to workspace-local storage.',resume:false})
   }})
   editor.add({name:'agent-evaluate',description:'Operator-only disposable evaluation assignment, JSON task contract; no model request.',execute:async({sessionID,prompt})=>{
    const root=await rootOf(sessionID);const info=unwrap(await ctx.session.get({sessionID}));const t=assignment(JSON.parse(prompt.text),limits.roles[info.agent]);need(t.to===info.agent&&root===sessionID,'Evaluation role/location mismatch')
    await transact(root,d=>{need(!d.tasks[t.id],'Task already initialized');t.status='RUNNING';d.tasks[t.id]=t;const s=getState(d,sessionID,t.to);s.taskID=t.id});await ctx.session.synthetic({sessionID,text:'Evaluation assignment initialized.',resume:false})
   }})
  })
  await ctx.session.hook('prompt',async event=>{
   const root=await rootOf(event.sessionID),info=unwrap(await ctx.session.get({sessionID:event.sessionID}))
   stopTimer(event.sessionID)
   await transact(root,d=>{const old=d.sessions[event.sessionID];const active=Object.values(d.tasks).find(t=>t.to===info.agent&&t.status==='RUNNING');
    d.sessions[event.sessionID]={role:info.agent,taskID:active?.id??old?.taskID??null,started:Date.now(),calls:0,searches:0,pages:0,sources:old?.sources??[],denied:0,modelSteps:0,closed:false}
   })
  })
  await ctx.session.hook('context',async event=>{
   const root=await rootOf(event.sessionID)
   const info=await transact(root,d=>{const s=getState(d,event.sessionID,event.agent);const t=taskFor(d,s);s.modelSteps=(s.modelSteps??0)+1;return {s:structuredClone(s),t:structuredClone(t)}})
   const {s,t}=info;arm(root,event.sessionID,s,t)
   event.options??={};event.options.maxTokens=event.agent==='researcher'||event.agent==='reviewer'?3000:4000
   const exhausted=s.closed||s.modelSteps>=t.budget.steps-3||s.calls>=t.budget.tools-1||Date.now()-s.started>=t.budget.seconds*1000
   if(event.tools)for(const name of Object.keys(event.tools))if(!native.has(name)||(name==='shell'&&!['poseidon','team-lead'].includes(event.agent))||(exhausted&&name!=='agent_contracts'))delete event.tools[name]
   event.system.push({type:'text',text:'Trusted task contract: '+JSON.stringify(t)+'. Submit findings using agent_contracts {action:"submit",value:{summary,status,claims:[],verification:[],uncertainty:[],nextAction}}. Routing is supplied automatically. Ordinary final prose is retained as an unreviewed PARTIAL handoff. Use help for public instructions and evidence for retrieved source excerpts; never read protected agent-control files. Word counts are advisory. Independent review is still required for material research. '+(exhausted?'Work budget exhausted: submit existing evidence as PARTIAL or INSUFFICIENT, or return your findings now; do not retry work tools.':'')})
  })
  await ctx.session.hook('retry',event=>{if(event.attempt>=1)event.decision={retry:false}})
  await ctx.session.hook('model.request',async event=>{
   const model=event.model?.id??''
   if(event.model?.providerID==='nvidia'||model.startsWith('nvidia/')||model.includes('nemotron'))await reserveNvidia(limits.providerLimits.nvidia)
  })
  await ctx.tool.transform(editor=>{
   for(const info of editor.list()){
    if(info.id==='agent_contracts')continue
    editor.update(info.id,tool=>{
     // Keep permitted tools on the native list when execute/Code Mode is denied.
     if(native.has(info.id))tool.options={...tool.options,codemode:false}
     if(info.id==='glob')tool.description='Bounded filename discovery within assigned paths, including named files. Patterns support *, ** and ?. Paths are relative to the project unless path is supplied. Protected paths, excluded files and symlinks are omitted.'
     if(['glob','subagent','webfetch'].includes(info.id))tool.output={type:'object',additionalProperties:true}
     const original=tool.execute;audit.set(info.id,{id:info.id,executor:typeof original==='function',recognized:native.has(info.id)})
     if(typeof original!=='function')return
     tool.execute=async(input,c)=>{
      const root=await rootOf(c.sessionID),role=c.agent??unwrap(await ctx.session.get({sessionID:c.sessionID})).agent
      let delegate
      const state=await transact(root,async d=>{
       const s=getState(d,c.sessionID,role),t=taskFor(d,s)
       try{
        need(!s.closed,'Task closed');need(info.id!=='grep','Native grep cannot enforce file exclusions; use project_search');need(s.calls<t.budget.tools-1,'Final tool slot reserved for handoff');need(native.has(info.id),'Unclassified tool denied: '+info.id)
        if(info.id==='shell')need(['poseidon','team-lead'].includes(role),'Host shell is restricted to top-level administration agents')
        if(info.id==='system_access'){
         if(input.action!=='connections')need(input.action==='public_fetch'?t.sourceTypes.includes('web'):input.action.startsWith('local_')?t.sourceTypes.includes('local'):t.sourceTypes.includes('system'),'Assignment must include the appropriate local/system source type')
         if(input.action==='local_command'&&!['poseidon','team-lead'].includes(role))need(s.taskID,'Local development commands require an assigned worker task')
        }
        if(info.id==='subagent'){
         need(role==='poseidon','Only Poseidon delegates');need(roles.includes(input.agent)&&input.agent!=='poseidon','Invalid delegation target')
         delegate=Object.values(d.tasks).find(x=>x.to===input.agent&&x.status==='ASSIGNED');need(delegate,'Validated assignment required before delegation');delegate.status='RUNNING'
         need(typeof input.prompt==='string','Unsupported subagent prompt schema');input={...input,background:false,prompt:input.prompt+'\nTrusted assignment: '+JSON.stringify(delegate)+'\nReturn findings using agent_contracts submit value {summary,status,claims:[],verification:[],uncertainty:[],nextAction}, or ordinary final prose. Routing is filled automatically. Do not propose_brief. Use source IDs from actual retrieval receipts; independent review remains required.'}
        }
        if(writes.has(info.id)){
         need((s.taskID||['poseidon','team-lead'].includes(role))&&t.to===role,'Local edits require a matching assigned task')
         for(const p of editPaths(input)){
          await scopedPath(ctx.location.directory,p,t,true)
          if(t.design||/\.(css|scss|sass|less|html?|tsx|jsx|vue|svelte)$/i.test(p)){
           const current=d.briefs[t.briefID]?.filter(b=>b.confirmed).at(-1)
           need(t.design&&current?.version===t.briefVersion&&(briefHash(current)===t.briefHash||digest(current)===t.briefHash),'Current confirmed design brief required for UI writes')
          }
         }
        }
        if(info.id==='read'){need(t.sourceTypes.includes('local'),'Local sources not approved');const p=input.path??input.filePath??input.file_path;let support=false;for(const skill of t.skills){try{const base=await realpath(fileURLToPath(new URL('../skills/'+skill+'/',import.meta.url)));const target=await realpath(path.resolve(ctx.location.directory,p));if(target.startsWith(base+path.sep))support=true}catch{}}if(!support)await scopedPath(ctx.location.directory,p,t)}
        if(info.id==='glob')need(t.sourceTypes.includes('local'),'Local sources not approved')
        if(info.id==='skill')need(t.skills.includes(input.id??input.name),'Skill not authorized by assignment')
        if(info.id==='websearch'||info.id==='webfetch')need(t.sourceTypes.includes('web'),'Web sources not approved')
        if(info.id.startsWith('opencode_'))need(t.sourceTypes.includes('mcp'),'MCP sources not approved')
        if(info.id==='question')need(role==='poseidon'||role==='team-lead','Only coordinator/design owner asks user questions')
        if(info.id==='poseidon_workspace')need(['settings','status'].includes(input.action)||(['poseidon','team-lead'].includes(role)&&['configure','test','end_sandbox'].includes(input.action)),'Top-level agents administer Docker tests; workers use isolated local_command and can inspect settings/status')
        spend(s,info.id,t.budget,Date.now());arm(root,c.sessionID,s,t)
        d.events.push({type:'admitted',tool:info.id,role,taskID:t.id});return {task:t,remaining:Math.max(1,t.budget.seconds*1000-(Date.now()-s.started))}
       }catch(e){d.events.push({type:'denied',tool:info.id,role});throw e}
      }).catch(async error=>{await transact(root,d=>{getState(d,c.sessionID,role).denied++});throw error})
      const timeout=AbortSignal.timeout(state.remaining);const signal=c.signal?AbortSignal.any([c.signal,timeout]):timeout
      let result
      try{
       if(info.id==='glob'){
        await ctx.permission.assert({sessionID:c.sessionID,agent:role,source:{type:'tool',messageID:c.messageID,id:c.id},action:'glob',resources:[input.pattern],save:[input.pattern]})
        const output=await discoverProject(ctx.location.directory,state.task,input,signal);result={output,content:JSON.stringify(output)}
       }else if(info.id==='webfetch'&&!['poseidon','team-lead'].includes(role))result=await systemInvoke({action:'public_fetch',url:input.url},{...c,agent:role,signal,_trustedTask:state.task})
       else result=await original(input,{...c,agent:role,signal,_trustedTask:state.task})
      }catch(e){if(!delegate)throw e;result={content:'Worker stopped: '+e.message}}
      if(info.id==='webfetch')result={...result,output:{content:sourceText(result)}}
      return transact(root,d=>{
       const s=getState(d,c.sessionID,role)
       if(delegate){
        const t=d.tasks[delegate.id];const worker=Object.values(d.sessions).find(x=>x.taskID===t.id)
        if(!worker?.modelHandoff){const report=sourceText(result).trim();const h=fallback(t,worker??{sources:[]},'Ordinary final report; not independently verified');if(report){h.summary=report.slice(0,16000);h.verification=[];h.uncertainty.push('Completion and factual claims require coordinator review');h.sources=worker?.sources??[]};t.handoff=h}
        t.handoff??=fallback(t,worker??{sources:[]},'Worker returned no report');t.status=t.handoff.status
        for(const [id,state]of Object.entries(d.sessions))if(state.taskID===t.id){state.closed=true;stopTimer(id)}
        return {...result,output:t.handoff,content:JSON.stringify(t.handoff)}
       }
       if(['read','project_search','webfetch','opencode_read_mcp_resource','system_access'].includes(info.id)&&s.sources.length<64){
        const content=sourceText(result),ref=(info.id==='system_access'?'System '+input.action+' '+(input.profile??'local'):undefined)??input.url??(info.id==='project_search'?'Local bounded search: '+input.query:undefined)??input.path??input.filePath??input.uri??'MCP resource';const source={id:'S'+(s.sources.length+1),ref,type:info.id==='read'?'LOCAL':'RETRIEVED',retrievedAt:new Date().toISOString(),sha256:createHash('sha256').update(content).digest('hex'),excerpt:content.slice(0,16000),truncated:content.length>16000};s.sources.push(source)
        const receipt={type:'text',text:'Evidence source ID: '+source.id+'. Use this ID in claims.sourceIDs; quotes are optional and checked when classifying factual evidence.'}
        return {...result,content:Array.isArray(result.content)?[receipt,...result.content]:receipt.text+'\n\n'+content}
       }
       return result
      })
     }
    })
   }
  })
  const lifecycle=new AbortController()
  const subscription=ctx.event?.subscribe ? (async()=>{
   for await(const event of ctx.event.subscribe({types:['session.execution.succeeded','session.execution.failed','session.execution.interrupted','session.deleted','session.archived'],signal:lifecycle.signal})){
    const id=event.data?.sessionID??event.sessionID
    if(!id||!timers.has(id))continue
    stopTimer(id)
    try{const root=await rootOf(id);await transact(root,d=>{const s=d.sessions[id];if(!s||s.closed)return;const t=taskFor(d,s);s.closed=true;s.handoff??=fallback(t,s,event.type);if(d.tasks[t.id]){d.tasks[t.id].handoff??=s.handoff;d.tasks[t.id].status=d.tasks[t.id].handoff.status}})}catch{}
   }
  })().catch(()=>{}) : Promise.resolve()
  return async()=>{lifecycle.abort();for(const id of timers.keys())stopTimer(id);await subscription;await Promise.allSettled([...locks.values()]);locks.clear();audit.clear()}
 }
}
