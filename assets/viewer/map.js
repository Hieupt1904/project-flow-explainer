/* Canvas coordinates, edge routing and viewport gestures. */
function createFlowMap(graph, model, select, elements) {
  const {viewport, world, layer, nodesLayer, minimap, zoomLabel}=elements;
  const width=295, height=164, lo=.001, hi=2;
  const cards=new Map(), miniNodes=new Map(), wires=[];
  const kinds=Object.keys(FlowModel.edgeKinds);
  const left=Math.min(...graph.nodes.map(n=>n.x))-48;
  const top=Math.min(...graph.nodes.map(n=>n.y))-70;
  const right=Math.max(...graph.nodes.map(n=>n.x+width))+48;
  const bottom=Math.max(...graph.nodes.map(n=>n.y+height))+72;
  const w=right-left,h=bottom-top;
  const points=new Map(graph.nodes.map(n=>[n.id,{x:n.x-left,y:n.y-top}]));
  let scale=1,x=0,y=0,drag=null,miniWindow;
  let frame=0;

  function marker(kind){
    const m=svg('marker',{id:'arrow-'+kind,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto'});
    m.append(svg('path',{d:'M 0 0 L 10 5 L 0 10 z',class:'arrow '+kind}));
    return m;
  }
  function number(n){return String(n+1).padStart(2,'0');}
  function makeCard(node,index){
    const p=points.get(node.id), button=element('button','node-card');
    button.type='button';button.dataset.id=node.id;button.dataset.type=node.type;
    button.style.left=p.x+'px';button.style.top=p.y+'px';
    button.setAttribute('aria-label',node.title);button.setAttribute('aria-pressed','false');
    button.onclick=()=>select(node.id);
    const head=add(button,'span','node-top');
    const kind=add(head,'span','node-kind');kind.append(icon(node.type),document.createTextNode(FlowModel.types[node.type]));
    add(head,'span','node-index',number(index));
    add(button,'span','node-title',node.title);
    add(button,'span','node-summary',node.summary);
    const foot=add(button,'span','node-bottom');
    add(foot,'span','label '+node.confidence,FlowModel.confidence[node.confidence]);
    const outgoing=model.outgoing.get(node.id).length;
    if(outgoing>1)add(foot,'span',null,outgoing+' nhánh');
    cards.set(node.id,button);nodesLayer.append(button);
  }
  const boxes=[...points.values()].map(p=>({x:p.x,y:p.y,w:width,h:height}));
  const labels=[];
  function collides(a,b){return a.x<b.x+b.w+5&&a.x+a.w+5>b.x&&a.y<b.y+b.h+5&&a.y+a.h+5>b.y;}
  function labelPoint(path,labelWidth){
    const length=path.getTotalLength();
    for(const t of [.5,.4,.6,.3,.7,.2,.8,.1,.9]){
      const p=path.getPointAtLength(t*length);
      for(const dy of [0,-24,24,-48,48,-70,70]){
        const box={x:p.x-labelWidth/2,y:p.y+dy-12,w:labelWidth,h:24};
        if(box.x<0||box.x+box.w>w||box.y<0||box.y+box.h>h)continue;
        if(!boxes.some(b=>collides(box,b))&&!labels.some(b=>collides(box,b))){labels.push(box);return box;}
      }
    }
    return null; // Full branch text remains in the inspector and guide.
  }
  function drawEdge(edge){
    const a=points.get(edge.from), b=points.get(edge.to);
    let d;
    if(edge.from===edge.to){
      const sx=a.x+width, sy=a.y+height*.7, ey=a.y+height*.34;
      d=['M',sx,sy,'C',sx+60,sy+43,sx+60,ey-43,sx,ey].join(' ');
    }else if(b.x>a.x+width+12){
      const sx=a.x+width, sy=a.y+height/2, ex=b.x, ey=b.y+height/2, gap=Math.max(40,(ex-sx)*.43);
      d=['M',sx,sy,'C',sx+gap,sy,ex-gap,ey,ex,ey].join(' ');
    }else if(b.x+width+12<a.x){
      const sx=a.x+width/2, ex=b.x+width/2, sy=a.y+height, ey=b.y+height;
      const lane=Math.max(sy,ey)+54;
      d=['M',sx,sy,'C',sx,sy+36,sx,lane,sx-38,lane,'H',ex+38,'C',ex,lane,ex,ey+36,ex,ey].join(' ');
    }else{
      const down=b.y>=a.y,sx=a.x+width/2,ex=b.x+width/2,sy=a.y+(down?height:0),ey=b.y+(down?0:height);
      const bend=down?64:-64;
      d=['M',sx,sy,'C',sx,sy+bend,ex,ey-bend,ex,ey].join(' ');
    }
    const group=svg('g',{class:'edge-set'}), path=svg('path',{d,class:'edge-path '+edge.kind,'marker-end':'url(#arrow-'+edge.kind+')'});
    group.append(path); layer.append(group);wires.push({edge,group,path});
  }
  function drawLabels(){
    // Place labels after measuring the rendered paths; never cover cards or other labels.
    for(const {edge,group,path} of wires){
      if(!edge.label)continue;
      const chars=Array.from(edge.label),text=chars.length>30?chars.slice(0,29).join('')+'…':edge.label;
      const label=svg('text',{class:'edge-label-text','text-anchor':'middle'});
      label.textContent=text;group.append(label);
      const box=labelPoint(path,Math.ceil(label.getComputedTextLength())+14);
      if(!box){label.remove();continue;}
      group.insertBefore(svg('rect',{x:box.x,y:box.y,width:box.w,height:box.h,rx:5,class:'edge-label-rect'}),label);
      label.setAttribute('x',box.x+box.w/2);label.setAttribute('y',box.y+16);
    }
  }
  function apply(){
    world.style.transform='translate('+x+'px,'+y+'px) scale('+scale+')';
    zoomLabel.textContent=(scale<.1?(scale*100).toFixed(1):Math.round(scale*100))+'%';
    const minX=Math.max(0,-x/scale),minY=Math.max(0,-y/scale);
    const maxX=Math.min(w,(viewport.clientWidth-x)/scale),maxY=Math.min(h,(viewport.clientHeight-y)/scale);
    miniWindow.setAttribute('x',minX);miniWindow.setAttribute('y',minY);
    miniWindow.setAttribute('width',Math.max(0,maxX-minX));miniWindow.setAttribute('height',Math.max(0,maxY-minY));
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(()=>{frame=0;apply();});}
  function center(px,py){x=viewport.clientWidth/2-px*scale;y=viewport.clientHeight/2-py*scale;apply();}
  function fit(){
    if(!viewport.clientWidth||!viewport.clientHeight)return;
    scale=Math.max(lo,Math.min(1,(viewport.clientWidth-18)/w,(viewport.clientHeight-24)/h));
    center(w/2,h/2);
  }
  function reveal(id){const p=points.get(id);if(!p||viewport.hidden)return;
    scale=Math.max(scale,Math.min(.83,(viewport.clientWidth-24)/width));center(p.x+width/2,p.y+height/2);
  }
  function zoom(mult,px=viewport.clientWidth/2,py=viewport.clientHeight/2){
    const value=Math.max(lo,Math.min(hi,scale*mult));
    x=px-(px-x)*value/scale;y=py-(py-y)*value/scale;scale=value;apply();
  }
  function highlight(id){
    const route=id?(model.pathTo(id)||[]):[], next=id?model.outgoing.get(id):[];
    const trace=new Set([...route,...next]);const neighbors=new Set(id?[id]:[]);
    for(const e of trace){neighbors.add(e.from);neighbors.add(e.to);}
    for(const [key,card] of cards){
      card.classList.toggle('is-selected',key===id);card.classList.toggle('is-dimmed',Boolean(id&&!neighbors.has(key)));
      card.setAttribute('aria-pressed',String(key===id));miniNodes.get(key).classList.toggle('is-selected',key===id);
    }
    for(const {edge,group} of wires){group.classList.toggle('is-dimmed',Boolean(id&&!trace.has(edge)));group.classList.toggle('is-trace',trace.has(edge));}
  }
  world.style.width=w+'px';world.style.height=h+'px';layer.setAttribute('width',w);layer.setAttribute('height',h);
  const defs=svg('defs');kinds.forEach(k=>defs.append(marker(k)));layer.append(defs);
  model.order.forEach((id,index)=>makeCard(model.nodes.get(id),index));graph.edges.forEach(drawEdge);drawLabels();
  minimap.setAttribute('viewBox',[0,0,w,h].join(' '));
  for(const [id,p] of points){const node=svg('rect',{x:p.x,y:p.y,width,height,rx:7,class:'mini-node','data-type':model.nodes.get(id).type});miniNodes.set(id,node);minimap.append(node);}
  miniWindow=svg('rect',{class:'mini-window'});minimap.append(miniWindow);
  minimap.parentElement.onclick=ev=>{
    if(ev.detail===0){fit();return;}
    const matrix=minimap.getScreenCTM();if(!matrix)return;
    const p=new DOMPoint(ev.clientX,ev.clientY).matrixTransform(matrix.inverse());
    center(Math.max(0,Math.min(w,p.x)),Math.max(0,Math.min(h,p.y)));
  };
  viewport.onpointerdown=ev=>{
    if(drag||ev.button!==0||ev.target.closest('.node-card'))return;
    drag={id:ev.pointerId,x:ev.clientX,y:ev.clientY,tx:x,ty:y};
    viewport.setPointerCapture(ev.pointerId);viewport.classList.add('panning');
  };
  viewport.onpointermove=ev=>{
    if(drag?.id!==ev.pointerId)return;
    x=drag.tx+ev.clientX-drag.x;y=drag.ty+ev.clientY-drag.y;schedule();
  };
  viewport.onlostpointercapture=()=>{drag=null;viewport.classList.remove('panning');};
  viewport.addEventListener('wheel',ev=>{ev.preventDefault();const r=viewport.getBoundingClientRect();zoom(ev.deltaY<0?1.15:1/1.15,ev.clientX-r.left,ev.clientY-r.top);},{passive:false});
  viewport.onkeydown=ev=>{
    if(ev.target!==viewport)return;
    const direction={ArrowLeft:[60,0],ArrowRight:[-60,0],ArrowUp:[0,60],ArrowDown:[0,-60]}[ev.key];
    if(direction){ev.preventDefault();x+=direction[0];y+=direction[1];apply();}
  };
  fit();
  return {fit,zoom,highlight,reveal};
}
