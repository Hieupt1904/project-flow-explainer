import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = fileURLToPath(new URL('..', import.meta.url));
const cli = path.join(root, 'scripts/project_map.mjs');
function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pfe-map-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const repo = path.join(dir, 'shop');
  fs.cpSync(path.join(root, 'tests/fixtures/shop-app'), repo, { recursive: true });
  assert.equal(spawnSync('git', ['init', '-q', repo]).status, 0);
  return {dir, repo, out:path.join(repo,'project-flow-explainer')};
}
test('rebrands and migrates an existing map without losing editable data', (t)=>{
  const {repo}=fixture(t);
  const legacy=path.join(repo,'floorplan'), current=path.join(repo,'project-flow-explainer');
  fs.mkdirSync(path.join(legacy,'descriptions'),{recursive:true});
  const architecture={$schema:'floorplan/architecture@1',project:{name:'Kho thử',summary:'Mô tả giữ nguyên'},nodes:[{id:'service',label:'Dịch vụ',kind:'service',paths:['server.js']}]};
  fs.writeFileSync(path.join(legacy,'architecture.json'),JSON.stringify(architecture));
  fs.writeFileSync(path.join(legacy,'descriptions','custom.json'),JSON.stringify({files:{'server.js':{name:'Điểm vào đã đặt tên',d:'Nhận yêu cầu'}}}));
  fs.writeFileSync(path.join(legacy,'custom-flows.json'),JSON.stringify({flows:[]}));
  assert.equal(success(run('build',repo)).artifacts.html,'project-flow-explainer/index.html');
  assert.ok(!fs.existsSync(legacy));
  assert.equal(JSON.parse(fs.readFileSync(path.join(current,'architecture.json'))).project.summary,architecture.project.summary);
  assert.ok(fs.existsSync(path.join(current,'custom-flows.json')));
  assert.match(fs.readFileSync(path.join(current,'index.html'),'utf8'),/alt="Project Flow Explainer"/);
  assert.doesNotMatch(fs.readFileSync(path.join(current,'index.html'),'utf8'),/haydenschmitty|alt="Floorplan"/);
});

test('leaves unrelated directories using a former map name in place', (t)=>{
  const {repo}=fixture(t);const legacy=path.join(repo,'floorplan');
  fs.mkdirSync(legacy);fs.writeFileSync(path.join(legacy,'keep.md'),'Dữ liệu khác');
  success(run('build',repo));
  assert.equal(fs.readFileSync(path.join(legacy,'keep.md'),'utf8'),'Dữ liệu khác');
});

function run(command, repo, ...args) {
  return spawnSync(process.execPath, [cli, command, repo, ...args], { encoding:'utf8' });
}
function success(result) {
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout);
}

test('map builds Project Flow Explainer navigation and an evidence-backed catalog of existing flows', (t) => {
  const {repo,out}=fixture(t);
  const built=spawnSync('python3',[path.join(root,'scripts/build_flow.py'),'--repo',repo,
    '--request','Giải thích luồng xuất báo cáo','--slug','bao-cao'], {encoding:'utf8'});
  assert.equal(built.status,0,built.stderr);
  const map=success(run('build',repo));
  assert.equal(map.artifacts.html,'project-flow-explainer/index.html');
  const graph=JSON.parse(fs.readFileSync(path.join(out,'graph.json'),'utf8'));
  assert.equal(graph.schema,'project-flow-explainer/graph@1');
  assert.ok(graph.files.some(f=>f.p==='services/report_service.js'));
  assert.ok(graph.routes.some(r=>r.p==='/api/reports/export'));
  assert.ok(graph.links.some(l=>l.k==='import'));
  assert.ok(graph.flows.some(f=>f.id.startsWith('pfe-bao-cao-')));
  assert.ok(graph.tour.length>=2);
  assert.ok(graph.health.issues instanceof Array);
  assert.equal(graph.meta.root,null);
  assert.ok(graph.meta.repos.every(r=>!Object.hasOwn(r,'remote')));
  const html=fs.readFileSync(path.join(out,'index.html'),'utf8');
  assert.match(html,/window.ProjectFlow = Object.freeze/);
  assert.match(html,/data-project-flow-explainer-policy="local"/);
  assert.doesNotMatch(html,new RegExp(repo.replace(/[.*+?^${}()|[]\\]/g,'\\$&')));
  const share=success(run('export',repo));
  const exported=fs.readFileSync(path.join(repo,share.artifacts.html),'utf8');
  assert.match(exported,/data-project-flow-explainer-policy="export"/);
  assert.match(exported,/connect-src 'none'/);
});

test('refresh retains edited inputs and records changed files', (t)=>{
  const {repo,out}=fixture(t);
  success(run('build',repo));
  const file=path.join(out,'architecture.json'), arch=JSON.parse(fs.readFileSync(file,'utf8'));
  arch.project.summary='Mô tả đã chỉnh tay';fs.writeFileSync(file,JSON.stringify(arch));
  fs.appendFileSync(path.join(repo,'server.js'),'\n// cập nhật nhỏ\n');
  success(run('refresh',repo));
  const graph=JSON.parse(fs.readFileSync(path.join(out,'graph.json'),'utf8'));
  assert.equal(graph.project.summary,'Mô tả đã chỉnh tay');
  assert.ok(graph.recent.items.some(item=>item.id==='f:server.js'));
});

test('blueprint creates planned screens and routes without creating application files', (t)=>{
  const {repo,out}=fixture(t);
  fs.mkdirSync(out);
  fs.copyFileSync(path.join(root,'tests/fixtures/project-map-blueprint.json'),path.join(out,'plan.json'));
  assert.equal(success(run('plan',repo)).blueprint,true);
  assert.equal(success(run('refresh',repo)).blueprint,true);
  const graph=JSON.parse(fs.readFileSync(path.join(out,'graph.json'),'utf8'));
  assert.ok(graph.meta.blueprint);
  assert.ok(graph.screens.some(screen=>screen.url==='/'));
  assert.ok(graph.routes.some(route=>route.p==='/reports'));
  assert.equal(fs.existsSync(path.join(repo,'web/index.tsx')),false);
});

test('does not follow a source symlink or write through a map symlink', {skip:process.platform==='win32'}, (t)=>{
  const {dir,repo,out}=fixture(t);
  const outside=path.join(dir,'outside.js');
  fs.writeFileSync(outside,'export function noOutsideCode() {}');
  fs.symlinkSync(outside,path.join(repo,'outside.js'));
  success(run('build',repo));
  assert.doesNotMatch(fs.readFileSync(path.join(out,'graph.json'),'utf8'),/noOutsideCode|outside.js/);
  fs.renameSync(out,out+'-saved');fs.symlinkSync(out+'-saved',out);
  assert.notEqual(run('refresh',repo).status,0);
});
