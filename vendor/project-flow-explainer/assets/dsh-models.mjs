// Import only model routes from DSH's composed profile. Credentials stay in DSH.
import { execFile } from 'node:child_process';
import { createRequire } from 'node:module';
import { promisify } from 'node:util';
import { mkdtempSync, writeFileSync, rmSync, realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const run = promisify(execFile);
const invocation = {shell:false,windowsHide:true,timeout:12000,maxBuffer:4*1024*1024};
const record = value => value && typeof value === 'object' && !Array.isArray(value);
const providerId = value => typeof value === 'string' && /^[a-z0-9][a-z0-9._-]{0,95}$/i.test(value) && !['__proto__','constructor','prototype'].includes(value);
const modelId = value => typeof value === 'string' && value.length > 0 && value.length <= 240 && /^[^\p{C}\s]+$/u.test(value);
const plainName = (value, fallback) => typeof value === 'string' && value.trim() && value.length <= 160 && !/[\p{C}@]/u.test(value) ? value : fallback;
const connectionKeys = ['apiKeyEnv','displayName','api','baseURL','models','modelOverrides','compat','defaultContextWindow','defaultMaxTokens','defaultInput','reasoning','thinkingBudgets','cacheRetention','transport','timeoutMs','retryPolicy','listing','maxTokens'];

function adapterConfig(source) {
  const destination = Object.fromEntries(connectionKeys.filter(key => Object.hasOwn(source,key)).map(key => [key,source[key]]));
  // A credential reference is a name, never a plaintext key. Do not inherit custom headers.
  if (typeof destination.apiKeyEnv !== 'string' || !/^[A-Z_][A-Z0-9_]{0,127}$/.test(destination.apiKeyEnv)) delete destination.apiKeyEnv;
  if (destination.baseURL !== undefined) {
    const url = new URL(destination.baseURL);
    if (!['https:','http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('Unsupported endpoint');
  }
  return destination;
}

export function projectCatalog(rows) {
  if (!Array.isArray(rows)) throw new Error('Expected DSH profile entries');
  const get = id => rows.find(row => row?.id === id && row.disabled !== true)?.config;
  const defaultRoute = get('agent-default-model');
  const routes=new Map();
  function add(provider, source, adapter) {
    if (!providerId(provider) || !record(source)) return;
    let config;
    try { config=adapterConfig(source); } catch { return; }
    for (const item of Array.isArray(config.models) ? config.models : []) {
      if (!record(item) || !modelId(item.id)) continue;
      const id=JSON.stringify([provider,item.id]);
      routes.set(id,{id,provider,model:item.id,name:plainName(item.name,item.id),adapter,config});
    }
  }
  for (const [provider, source] of Object.entries(get('llm-pi-ai')?.providers || {})) add(provider,source,'llm-pi-ai');
  add('deepseek-official',get('llm-deepseek'),'llm-deepseek');
  const defaultId=JSON.stringify([defaultRoute?.provider,defaultRoute?.model]);
  return { routes, defaultId:routes.has(defaultId) ? defaultId : null,
    models:[...routes.values()].map(({id,provider,model,name})=>({id,provider,model,name})) };
}

export async function readDshCatalog(cli, profile, cwd) {
  const { stdout }=await run(cli.cmd,[...cli.args,'--profile',profile,'--dump-config'],{cwd,encoding:'utf8',...invocation,env:{...process.env,PROJECT_FLOW_DSH_PROFILE:profile}});
  let rows;
  try { rows=JSON.parse(stdout); }
  catch {
    // Use DSH's installed parser in data-only mode. Never evaluate its !!js tags.
    const yaml=createRequire(realpathSync(cli.path))('yaml');
    const doc=yaml.parseDocument(stdout,{logLevel:'silent'});
    if (doc.errors.length) throw new Error('Invalid DSH configuration');
    rows=doc.toJS({maxAliasCount:50});
  }
  return projectCatalog(rows);
}

export function createDshOverlay(choice) {
  const rows=[{id:'credentials',disabled:false},{id:'authorization',disabled:false},{id:'deepseek-account',disabled:false}];
  if (choice) {
    rows.push({id:choice.adapter,disabled:false,config:choice.adapter==='llm-pi-ai'?{providers:{[choice.provider]:choice.config}}:choice.config});
    rows.push({id:'agent-default-model',config:{provider:choice.provider,model:choice.model}});
  }
  const dir=mkdtempSync(path.join(tmpdir(),'pfe-dsh-'));
  const file=path.join(dir,'selection.json');
  const dispose=()=>rmSync(dir,{recursive:true,force:true});
  try { writeFileSync(file,JSON.stringify(rows),{mode:0o600}); }
  catch(error) { dispose(); throw error; }
  return {file,dispose};
}
