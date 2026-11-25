#!/usr/bin/env node
/** Stable command entry for the vendored Project Flow Explainer. */
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {autoArchitecture} from '../vendor/project-flow-explainer/scripts/lib/pfe-bridge.mjs';
import {gitRun, legacyMapDir, MAP_DIR} from '../vendor/project-flow-explainer/scripts/lib/common.mjs';

const scripts=fileURLToPath(new URL('../vendor/project-flow-explainer/scripts/',import.meta.url));
const commands=new Set(['scan','build','refresh','describe','recent','status','plan','from-code','serve','export']);
const usage='node scripts/project_map.mjs <scan|build|refresh|describe|recent|status|plan|from-code|serve|export> <repo tuyệt đối>';
const [command, input, ...options]=process.argv.slice(2);
const output=(object)=>console.log(JSON.stringify(object));
function fail(code,message){const err=new Error(message);err.code=code;throw err;}
function assertMapDirectory(dir){
  if(!fs.existsSync(dir)){
    if(fs.readdirSync(path.dirname(dir)).includes(path.basename(dir)))fail('map_link','Thư mục bản đồ là liên kết hỏng.');
    return;
  }
  const stat=fs.lstatSync(dir);
  if(stat.isSymbolicLink()||!stat.isDirectory())fail('map_link','Thư mục bản đồ phải là thư mục thật.');
  const entries=fs.readdirSync(dir);
  if(entries.length&&!['architecture.json','plan.json','graph.json','.cache'].some(name=>entries.includes(name)))fail('map_conflict','Thư mục project-flow-explainer/ đã dùng cho dữ liệu khác.');
  if(fs.readdirSync(dir,{withFileTypes:true}).some(item=>item.isSymbolicLink()))fail('map_link','Thư mục bản đồ chứa liên kết tượng trưng.');
  for(const sub of ['.cache','descriptions']){
    const current=path.join(dir,sub);
    if(!fs.existsSync(current))continue;
    for(const item of fs.readdirSync(current,{withFileTypes:true}))if(item.isSymbolicLink())fail('map_link','Thư mục dữ liệu bản đồ chứa liên kết tượng trưng.');
    for(const name of ['worksheets','history']){
      const child=path.join(current,name);
      if(fs.existsSync(child)&&fs.statSync(child).isDirectory()&&fs.readdirSync(child,{withFileTypes:true}).some(x=>x.isSymbolicLink()))fail('map_link','Dữ liệu bản đồ chứa liên kết tượng trưng.');
    }
  }
}
function spawn(file,args,cwd,inherit=false){
  const result=spawnSync(process.execPath,[file,...args],{
    cwd,encoding:'utf8',stdio:inherit?'inherit':['ignore','pipe','pipe'],
    env:{...process.env,PROJECT_FLOW_UNATTENDED:'1'},maxBuffer:16*1024*1024,
  });
  if(result.error)fail('map_process_failed','Trình dựng dừng: '+result.error.code);
  return result;
}
function run(file,args,repo,{json=true}={}){
  const result=spawn(path.join(scripts,file+'.mjs'),[repo,...args,...(json?['--json']:[])],repo);
  let payload;try{payload=json?JSON.parse(result.stdout):{report:result.stdout};}catch{}
  if(result.status!==0||!payload)fail('map_'+file.replace('-','_')+'_failed',payload?.errors?.[0]||'Trình Project Flow Explainer báo lỗi. Kiểm tra dữ liệu đầu vào tại project-flow-explainer/.');
  return payload;
}
function saveNew(file,value){fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n',{flag:'wx'});}
function summarize(result,extra={}){
  return {status:'ok',kind:'project-flow-explainer',artifacts:{html:'project-flow-explainer/index.html',graph:'project-flow-explainer/graph.json',architecture:'project-flow-explainer/architecture.json'},
    counts:{files:result.files?.total??0,routes:result.descriptions?.routes?.total??0,modules:result.nodes?.length??0,links:result.links?.total??0},blueprint:!!result.blueprint,...extra};
}
try{
  if(!commands.has(command)||!input||!path.isAbsolute(input))fail('map_usage',usage);
  if(command!=='serve'&&options.length)fail('map_option','Lệnh này chỉ nhận đường dẫn kho mã.');
  const flags=new Set();
  for(let i=0;i<options.length;i++){
    const flag=options[i];
    if(flags.has(flag)||!['--agent','--port'].includes(flag))fail('map_option','Lệnh serve nhận --agent và --port.');
    flags.add(flag);
    if(flag==='--port'){const value=options[++i];if(!/^[0-9]{1,5}$/.test(value??'')||Number(value)>65535)fail('map_option','Cổng phải là số nguyên từ 0 đến 65535.');}
  }
  const repo=fs.realpathSync(input);if(!fs.statSync(repo).isDirectory())fail('map_repository','Chọn thư mục kho mã.');
  const dir=path.join(repo,MAP_DIR);assertMapDirectory(dir);
  if(!fs.existsSync(dir)&&['build','refresh','plan','from-code'].includes(command)){
    const previous=legacyMapDir(repo);
    if(previous){
      assertMapDirectory(previous);
      const inside=gitRun(repo,['rev-parse','--is-inside-work-tree']).out;
      if(inside==='true'){
        const tracked=gitRun(repo,['ls-files','--',path.basename(previous)+'/']);
        if(tracked.out!==''||tracked.error)fail('map_migration_tracked','Thư mục bản đồ cũ có tệp Git theo dõi hoặc chưa kiểm tra được. Hãy sao lưu và chuyển dữ liệu sang '+MAP_DIR+'/.');
      }
      fs.renameSync(previous,dir);
    }
  }
  const scanFile=path.join(dir,'.cache','scan.json'),archFile=path.join(dir,'architecture.json'),planFile=path.join(dir,'plan.json');
  if(command==='status'){output(run('status',[],repo));}
  else if(command==='scan'){const scan=run('scan',[],repo);output({status:'ok',summary:scan.summary,artifact:'project-flow-explainer/.cache/scan.json'});}
  else if(command==='describe'||command==='recent'){output(run(command,[],repo));}
  else if(command==='serve'||command==='export'){
    if(!fs.existsSync(path.join(dir,'index.html')))fail('map_missing','Dựng bản đồ trước.');
    const argv=command==='export'?['--export',path.join(dir,'share.html')]:['--no-open',...options];
    const result=spawn(path.join(scripts,'../assets/serve.mjs'),['--directory',dir,...argv],repo,command==='serve');
    if(result.status!==0)fail('map_'+command+'_failed','Máy chủ hoặc lệnh xuất bản đồ báo lỗi.');
    if(command==='export')output({status:'ok',artifacts:{html:'project-flow-explainer/share.html'}});
  }else{
    if(command==='from-code'||(command==='refresh'&&fs.existsSync(path.join(dir,'graph.json')))){
      const res=run('refresh',command==='from-code'?['--from-code']:[],repo);output(summarize(res.build,{next:res.next||[]}));
    }else{
      const blueprint=command==='plan'||fs.existsSync(planFile)&&(!fs.existsSync(scanFile)||Boolean(JSON.parse(fs.readFileSync(scanFile,'utf8')).blueprint));
      if(blueprint)run('plan',[],repo,{json:false});else run('scan',[],repo);
      const scan=JSON.parse(fs.readFileSync(scanFile,'utf8'));
      if(!fs.existsSync(archFile))saveNew(archFile,autoArchitecture(scan));
      output(summarize(run('build',['--agent','dsh'],repo)));
    }
  }
}catch(error){output({status:'error',code:error.code||'map_failed',message:error.message});process.exitCode=2;}
