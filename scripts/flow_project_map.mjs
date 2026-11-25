#!/usr/bin/env node
// Read a validated PFE flow from stdin and render a self-contained Project Flow Explainer page.
import fs from 'node:fs';
import {renderPage} from '../vendor/project-flow-explainer/assets/render-page.mjs';
const g=JSON.parse(fs.readFileSync(0,'utf8'));
const groups={start:'service',message:'ui',action:'feature',decision:'worker',data:'data',end:'service',error:'infra',external:'external'};
const keys=new Map(g.nodes.map(n=>[n.id,'step-'+n.id]));
const paths=[...new Set(g.nodes.flatMap(n=>(n.source_refs||[]).map(r=>r.path)))];
const graph={schema:'project-flow-explainer/graph@1',meta:{root:null,rootName:g.flow_id,audience:'everyone',agent:'dsh',repos:[],counts:{files:paths.length,loc:0,unassigned:0}},
  project:{name:g.title,summary:g.description,entrypoints:[]},
  nodes:g.nodes.map(n=>({id:keys.get(n.id),parent:null,label:n.title,summary:n.summary,kind:groups[n.type],details:n.details||'',tags:[],paths:[],stats:{files:0,loc:0,langs:{},repos:[]}})),
  files:[],routes:[],screens:[],flows:[],tour:[],
  links:g.edges.filter(e=>e.from!==e.to).map(e=>({a:'n:'+keys.get(e.from),b:'n:'+keys.get(e.to),k:'step',w:1,labels:e.label?[e.label]:[],desc:e.technical||'',inferred:e.evidence!=='call'})),
  pfeFlow:g};
const entry=g.nodes.find(n=>n.id===g.entry_node);
graph.tour=[{ref:'root',title:g.title,note:'Sơ đồ giải thích một luồng; không phải bản đồ toàn kho.'},
  ...(entry?[{ref:'n:'+keys.get(entry.id),title:entry.title,note:entry.summary}]:[])];
process.stdout.write(renderPage(graph,'export'));
