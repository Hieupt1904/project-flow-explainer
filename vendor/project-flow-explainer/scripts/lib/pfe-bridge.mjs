// Project Flow Explainer glue for the vendored Project Flow Explainer engine.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {maskSecrets} from './health.mjs';

const groups = {
  ui: ['Giao diện', 'Mã hiển thị và điều hướng cho người dùng.'],
  service: ['Điểm vào và dịch vụ', 'Mã nhận yêu cầu hoặc thực thi tác vụ của ứng dụng.'],
  worker: ['Tác vụ nền', 'Mã trong các thư mục dành cho tác vụ nền.'],
  data: ['Dữ liệu', 'Mã và tệp cấu hình nằm trong khu vực dữ liệu.'],
  library: ['Mô-đun dùng chung', 'Các thư mục mã được nhóm theo vị trí trong kho.'],
  script: ['Công cụ vận hành', 'Các lệnh và script dùng với kho mã.'],
  test: ['Kiểm thử', 'Các tệp kiểm thử và dữ liệu mẫu.'],
  config: ['Cấu hình', 'Các tệp cấu hình mà trình quét đã nhận diện.'],
};
const testName=/(^|\/)(tests?|specs?|__tests__)(\/|$)|[._](test|spec)\.|(^|\/)test_[^/]+$/i;
export const skipFile = rel => /(^|\/)(?:\.(?:env(?:\.[^/]*)?|netrc|npmrc|pypirc|pgpass)|[^/]*(?:credentials?|secrets?)[^/]*\.(?:json|ya?ml|toml|ini)|id_(?:rsa|ed25519|ecdsa|dsa)|[^/]+\.(?:pem|key|p12|pfx|keystore|tfvars))($|\/)/i.test(rel);
export function dataPath(root,rel){
  if(typeof rel!=='string'||!rel||rel.includes('\\')||rel.includes(':')||path.isAbsolute(rel)||rel.split('/').some(p=>!p||p==='.'||p==='..'))return null;
  let file=root;
  try{for(const part of rel.split('/')){file=path.join(file,part);if(fs.lstatSync(file).isSymbolicLink())return null;}return fs.statSync(file).isFile()?file:null;}catch{return null;}
}
export function autoArchitecture(scan){
  const files=scan.files.filter(f=>f.category==='code'||f.category==='config');
  const entries=new Set([...scan.routes.map(r=>r.file),...files.filter(f=>/(^|\/)(?:server|app|main|__main__|cli|index)\.[a-z]+$/i.test(f.path)).map(f=>f.path)]);
  const nodes=[], buckets=new Map();
  for(const f of files){
    const parts=f.path.split('/'), first=parts[0];
    const group=f.category==='config'?'config':testName.test(f.path)?'test':
      (f.screens?.length||parts.some(x=>/^(ui|web|pages|frontend|views|components|templates)$/i.test(x)))?'ui':
      parts.some(x=>/^(db|sql|models|migrations|data|repositories)$/i.test(x))?'data':
      parts.some(x=>/^(jobs|workers|tasks|queues)$/i.test(x))?'worker':
      parts.some(x=>/^(scripts|tools|bin)$/i.test(x))?'script':
      entries.has(f.path)||parts.some(x=>/^(routes|server|api|backend|services|handlers|controllers)$/i.test(x))?'service':'library';
    if(!buckets.has(group))buckets.set(group,new Map());
    const sections=buckets.get(group), name=parts.length>1?first:'(gốc)';
    if(!sections.has(name))sections.set(name,[]);sections.get(name).push(f.path);
  }
  for(const [group,sections] of buckets){
    const [label,summary]=groups[group];
    const node={id:group,label,summary,kind:group,paths:[]};nodes.push(node);
    // Each child claims exact scan paths; a broad directory glob would steal
    // files belonging to another group when the same directory is mixed.
    const only=sections.size===1;
    for(const [name,paths] of sections){
      const id=group+'.'+createHash('sha256').update(name).digest('hex').slice(0,10);
      const owner=only?node:{id,parent:group,label:name==='(gốc)'?'Tệp ở thư mục gốc':name,kind:group,summary:'Các tệp thuộc nhóm '+label.toLowerCase()+'.',paths:[]};
      if(!only)nodes.push(owner);
      owner.paths=paths.filter(p=>!/[?*{]/.test(p)&&p.length<=300).slice(0,500);
    }
  }
  const hosts=[...new Set(scan.hosts.map(h=>h.host))].filter(h=>/^[a-z0-9.-]{1,120}$/i.test(h)).slice(0,12);
  for(const host of hosts)nodes.push({id:'ext-'+createHash('sha256').update(host).digest('hex').slice(0,12),label:host,kind:'external',summary:'Máy chủ xuất hiện trong yêu cầu mà trình quét nhận diện.',hosts:[host]});
  return {$schema:'project-flow-explainer/architecture@1',project:{name:scan.rootName,summary:'Sơ đồ tạo từ mã nguồn. Các nhóm tự động dựa trên thư mục, điểm vào và loại tệp.',entrypoints:[...entries].slice(0,12)},audience:'everyone',include:['code','config'],nodes,edges:[],flows:[],tour:nodes.filter(n=>!n.parent).slice(0,7).map(n=>({node:n.id,title:n.label,note:n.summary}))};
}

function readJson(file){return JSON.parse(fs.readFileSync(file,'utf8'));}
function clean(value){return typeof value==='string'?maskSecrets(value).replace(/(?:[A-Za-z]:[\\/]|\/(?:home|Users|tmp|private|mnt|var)\/)[^\s\x60"'<>]+/g,'[đường dẫn cục bộ]'):'';}
export function appendEvidenceFlows(root,included,outFlows){
  const base=path.join(root,'artifacts','flows');let names;
  try{if(fs.realpathSync(base)!==base)return;names=fs.readdirSync(base).sort().slice(0,150);}catch{return;}
  for(const slug of names){
    if(!/^[a-zA-Z0-9_-]{1,80}$/.test(slug))continue;
    const file=dataPath(root,'artifacts/flows/'+slug+'/flow.json');if(!file)continue;
    let graph;try{if(fs.statSync(file).size>2_000_000)continue;graph=readJson(file);}catch{continue;}
    if(!Array.isArray(graph?.nodes)||!Array.isArray(graph?.edges)||graph.nodes.length>250||graph.edges.length>600)continue;
    const nodes=new Map(graph.nodes.filter(n=>n&&typeof n.id==='string').map(n=>[n.id,n]));
    const next=new Map([...nodes.keys()].map(id=>[id,[]]));
    for(const edge of graph.edges)if(edge&&next.has(edge.from)&&nodes.has(edge.to))next.get(edge.from).push(edge);
    const queue=[[graph.entry_node,[],new Set()]];
    let route=0, visited=0;
    while(queue.length&&route<10&&visited++<1800){
      const [id, steps, seen]=queue.pop();const node=nodes.get(id);if(!node||seen.has(id)||seen.size>=60)continue;
      const source=Array.isArray(node.source_refs)&&node.source_refs.find(s=>s&&included.has(s.path));
      const note=[clean(node.title),clean(node.summary),source?source.path+(source.start_line?':'+source.start_line:''):'',clean(node.confidence)].filter(Boolean).join(' · ');
      const list=source?[...steps,{ref:'f:'+source.path,note}]:steps;
      const edges=next.get(id).filter(edge=>edge.kind!=='loop'&&!seen.has(edge.to));
      if(edges.length){const walked=new Set([...seen,id]);for(const edge of edges.slice().reverse()){
        const withBranch=list.length&&edge.label?[...list.slice(0,-1),{...list.at(-1),note:list.at(-1).note+' · '+clean(edge.label)}]:list;
        queue.push([edge.to,withBranch,walked]);
      }}else if(list.length>=2){
        route++;const id='pfe-'+slug+'-'+route;
        if(!outFlows.some(f=>f.id===id))outFlows.push({id,title:clean(graph.title||slug)+(route>1?' · Nhánh '+route:''),description:'Đối chiếu từ sơ đồ Project Flow Explainer. Căn cứ tĩnh không xác nhận hành vi khi chạy.',steps:list});
      }
    }
  }
}

export function recentFromScan(previous, graph){
  if(!previous)return null;
  const old=new Map(previous.files.map(f=>[f.p,f.h]));
  const items=graph.files.filter(f=>f.h&&(!old.has(f.p)||old.get(f.p)!==f.h)).slice(0,50).map(f=>({id:'f:'+f.p,task:0,change:old.has(f.p)?'changed':'new',note:old.has(f.p)?'Nội dung tệp khác lần dựng trước.':'Tệp mới xuất hiện trên bản đồ.'}));
  return items.length?{updatedAt:new Date().toISOString(),tasks:[{title:'Thay đổi từ lần dựng trước',request:'',summary:'So sánh dấu vân tay của các tệp có trong bản đồ.',status:''}],items}:null;
}
