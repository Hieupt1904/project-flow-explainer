/* Workspace controls and inspector. */
(()=>{
  const originalDocument='<!doctype html>\n'+document.documentElement.outerHTML;
  const $=byId, graph=JSON.parse($('workflow-json').textContent), model=FlowModel.createModel(graph);
  const {types,confidence,edgeKinds,locationOf,edgeEvidence}=FlowModel;
  const root=$('inspection-content'), search=$('search'), results=$('search-results'), workspace=$('workspace');
  const small=matchMedia('(max-width:720px)'), systemTheme=matchMedia('(prefers-color-scheme:dark)');
  let tab='overview', mode='technical', selected=null, level='', history=[];
  document.querySelectorAll('[data-icon]').forEach(node=>node.append(icon(node.dataset.icon)));
  document.title=graph.title+' | Project Flow Explainer';$('flow-title').textContent=graph.title;
  $('flow-description').textContent=graph.description;
  const meta=graph.meta&&typeof graph.meta==='object'?graph.meta:{};
  const source=meta.source&&typeof meta.source==='object'?meta.source:{};
  const demo=(model.confidenceCounts.get('illustrative')||0)===graph.nodes.length;
  $('build-label').textContent=demo?'Ví dụ minh họa':'Xem ngoại tuyến';
  const canvas=createFlowMap(graph,model,id=>inspect(id,{reveal:false}),{
    viewport:$('viewport'),world:$('world'),layer:$('edge-layer'),nodesLayer:$('nodes-layer'),minimap:$('minimap'),zoomLabel:$('zoom-level'),
  });
  function announce(text){$('announcement').textContent=text;}
  function section(title,parent=root){const block=add(parent,'section','inspect-section');add(block,'h3',null,title);return block;}
  function facts(items){const list=add(root,'dl','facts');for(const [key,value] of items){add(list,'dt',null,key);add(list,'dd',null,value);}}
  function setPanel(open){
    $('inspector').hidden=!open;workspace.classList.toggle('panel-hidden',!open);
    $('panel-toggle').setAttribute('aria-expanded',String(open));
    if(mode==='technical')requestAnimationFrame(()=>selected?canvas.reveal(selected):canvas.fit());
  }
  function setMode(next){
    mode=next;const mapped=mode==='technical';
    $('view-technical').setAttribute('aria-pressed',String(mapped));$('view-simple').setAttribute('aria-pressed',String(!mapped));
    $('viewport').hidden=!mapped;$('canvas-controls').hidden=!mapped;$('simple-view').hidden=mapped;
    if(!mapped){closeGuide(false);renderSteps();}
    else if(selected)canvas.reveal(selected);else canvas.fit();
  }
  function heading(name){add(root,'h2',null,name);}
  function openTab(next){
    tab=next;
    for(const name of ['overview','details','evidence'])$('tab-'+name).setAttribute('aria-pressed',String(name===tab));
    root.replaceChildren();root.scrollTop=0;
    if(tab==='overview')overview();else if(tab==='details')details();else evidence();
  }
  function statusGroups(){
    const block=section('Mức độ căn cứ'), list=add(block,'div','status-list');
    for(const [key,value] of model.confidenceCounts){
      if(!value)continue;
      const cmd=button(list,'',()=>{level=level===key?'':key;closeSearch();setMode('simple');openTab('evidence');},'');
      cmd.setAttribute('aria-pressed',String(level===key));
      add(cmd,'span','label '+key,confidence[key]);add(cmd,'span',null,value);
    }
  }
  function overview(){
    heading('Tổng quan luồng');
    add(root,'p',null,demo?'Đây là sơ đồ minh họa. Các bước không phản ánh mã nguồn thực tế.':'Chọn một bước để xem cách đi tiếp và đối chiếu vị trí trong mã nguồn.');
    const actions=add(root,'div','inspector-actions');
    button(actions,'Xem điểm bắt đầu',()=>inspect(graph.entry_node));
    if(selected)button(actions,'Bỏ chọn',()=>{selected=null;canvas.highlight(null);openTab('overview');if(mode==='simple')renderSteps();});
    facts([['Điểm bắt đầu',model.nodes.get(graph.entry_node).title],['Số bước',graph.nodes.length],['Đường nối',graph.edges.length],['Vị trí nguồn',model.sources.length]]);
    statusGroups();
    if(graph.scope||graph.audience||source.commit){
      const block=section('Phạm vi');
      if(graph.scope)add(block,'p',null,graph.scope);
      if(graph.audience)add(block,'p',null,graph.audience);
      if(source.commit){const line=add(block,'p');line.append('Commit ',element('code',null,source.commit));}
      if(source.dirty===true)add(block,'p','hint','Kho mã có thay đổi chưa ghi vào Git khi dựng sơ đồ.');
    }
  }
  function branch(root,edge,onSelect){
    const target=model.nodes.get(edge.to);
    const cmd=button(root,'',onSelect,'branch-button');
    add(cmd,'span',null,edge.label||edgeKinds[edge.kind]);
    add(cmd,'small',null,target.title+(edge.kind==='normal'?'':' · '+edgeKinds[edge.kind]));
    return cmd;
  }
  function details(){
    if(!selected){heading('Chọn một bước');add(root,'p',null,'Chọn một nút trên bản đồ hoặc tìm theo tên bước, nhánh hay tệp.');return;}
    const node=model.nodes.get(selected);
    badge(root,node.confidence);heading(node.title);add(root,'p',null,node.summary);
    const actions=add(root,'div','inspector-actions');
    button(actions,mode==='technical'?'Định vị bước':'Mở trên bản đồ',()=>{setMode('technical');canvas.reveal(node.id);});
    button(actions,'Bỏ chọn',()=>{selected=null;canvas.highlight(null);openTab('overview');if(mode==='simple')renderSteps();});
    if(node.actor)add(section('Ai thực hiện?'),'p',null,node.actor);
    if(node.details)add(section('Diễn giải'),'p',null,node.details);
    const outgoing=model.outgoing.get(node.id);
    if(outgoing.length){
      const block=section('Đi tiếp khi nào?');
      for(const edge of outgoing){
        branch(block,edge,()=>inspect(edge.to,{focusPanel:true}));
        add(block,'p','hint',edgeEvidence(edge.evidence));
        if(edge.technical)add(add(block,'p','edge-technical'),'code',null,edge.technical);
      }
    }else add(section('Đi tiếp khi nào?'),'p',null,'Sơ đồ không có đường nối đi tiếp từ bước này.');
    if(node.technical)add(add(section('Chi tiết kỹ thuật'),'p'),'code',null,node.technical);
    if(node.source_refs?.length){
      const list=add(section('Căn cứ trong mã nguồn'),'ul','plain-list');
      for(const ref of node.source_refs){
        const item=add(list,'li');add(item,'code',null,locationOf(ref));
        if(ref.symbol)add(add(item,'p','hint'),'code',null,ref.symbol);
      }
    }else add(section('Căn cứ trong mã nguồn'),'p','hint','Sơ đồ chưa nêu tệp và dòng mã cho bước này.');
  }
  function evidence(){
    heading('Căn cứ và giới hạn');
    add(root,'p',null,'Căn cứ tĩnh cho biết vị trí hoặc quan hệ trong mã nguồn. Căn cứ này không chứng minh hành vi khi chạy.');
    statusGroups();
    const refs=section('Vị trí trong mã nguồn');
    if(!model.sources.length)add(refs,'p',null,'Sơ đồ chưa có vị trí mã nguồn để đối chiếu.');
    const list=add(refs,'ul','plain-list');
    for(const ref of model.sources){
      const item=add(list,'li');add(item,'code',null,ref.location);
      const links=add(item,'div','ref-links');
      for(const node of ref.nodes)button(links,node.title,()=>inspect(node.id,{focusPanel:true}));
    }
    if(Array.isArray(meta.related)&&meta.related.some(ref=>ref&&typeof ref.path==='string')){
      const block=section('Tệp liên quan ngoài luồng');
      add(block,'p','hint','Các tệp này không nằm trên đường nối của sơ đồ.');
      const files=add(block,'ul','plain-list');
      for(const ref of meta.related){if(!ref||typeof ref.path!=='string')continue;const item=add(files,'li');add(item,'code',null,ref.path);if(typeof ref.reason==='string')add(item,'p','hint',ref.reason);}
    }
    if(graph.assumptions?.length){const list=add(section('Điểm cần xác nhận'),'ul');for(const note of graph.assumptions)add(list,'li',null,note);}
    if(typeof graph.notes==='string'&&graph.notes) add(section('Ghi chú'),'p',null,graph.notes);
  }
  function inspect(id,options={}){
    if(!model.nodes.has(id))return;
    selected=id;
    // A guide path is explicit. Selecting outside the guide ends that session.
    if(!options.guided)closeGuide(false);
    if($('inspector').hidden)setPanel(true);
    canvas.highlight(id);if(options.reveal!==false&&mode==='technical')canvas.reveal(id);
    openTab('details');if(mode==='simple')renderSteps();
    if(options.focusPanel||(!options.guided&&small.matches)){
      root.focus({preventScroll:true});if(small.matches)$('inspector').scrollIntoView({block:'nearest'});
    }
    announce('Đã chọn '+model.nodes.get(id).title);
  }
  const stepIndex=new Map(model.order.map((id,i)=>[id,i+1]));
  function renderSteps(){
    const target=$('simple-view');target.replaceChildren();
    const items=model.search(search.value,level);
    if(level){const bar=add(target,'div','active-filter');add(bar,'span',null,confidence[level]);button(bar,'Bỏ lọc',()=>{level='';renderSteps();if(tab!=='details')openTab(tab);});}
    if(!items.length){add(target,'p','empty-list','Không có bước nào khớp. Hãy đổi từ khóa hoặc bỏ lọc.');return;}
    const list=add(target,'ol','step-list');
    for(const node of items){
      const row=add(list,'li','step-row'+(node.id===selected?' is-selected':''));
      add(row,'span',null,String(stepIndex.get(node.id)).padStart(2,'0'));
      const body=add(row,'div');button(body,node.title,()=>inspect(node.id,{focusPanel:true}),'');add(body,'p',null,node.summary);
      badge(row,node.confidence);
    }
  }
  function closeSearch(){results.hidden=true;search.setAttribute('aria-expanded','false');}
  function resultsForInput(){
    const query=search.value.trim();
    if(mode==='simple')renderSteps();
    results.replaceChildren();if(!query){closeSearch();return;}
    const all=model.search(query), list=all.slice(0,8);
    results.hidden=false;search.setAttribute('aria-expanded','true');
    add(results,'p',null,!all.length?'Không có bước nào khớp.':all.length>list.length?'Hiện '+list.length+' trên '+all.length+' bước':all.length+' bước phù hợp');
    for(const node of list){
      const cmd=button(results,node.title,()=>{closeSearch();inspect(node.id,{focusPanel:true});},'');
      add(cmd,'span',null,types[node.type]+' · '+confidence[node.confidence]);
    }
  }
  search.oninput=resultsForInput;
  search.onfocus=()=>{if(search.value.trim())resultsForInput();};
  search.onkeydown=ev=>{
    if(ev.key==='Enter'&&search.value.trim()&&!results.hidden){ev.preventDefault();results.querySelector('button')?.click();}
    if(ev.key==='ArrowDown'&&!results.hidden){ev.preventDefault();results.querySelector('button')?.focus();}
  };
  results.onkeydown=ev=>{
    if(ev.key!=='ArrowDown'&&ev.key!=='ArrowUp')return;
    ev.preventDefault();const buttons=[...results.querySelectorAll('button')], i=buttons.indexOf(document.activeElement)+(ev.key==='ArrowDown'?1:-1);
    (buttons[i]||search).focus();
  };
  document.addEventListener('focusin',ev=>{if(!ev.target.closest('.global-search'))closeSearch();});
  document.addEventListener('pointerdown',ev=>{if(!ev.target.closest('.global-search'))closeSearch();});

  function renderGuide(focusChoice){
    const id=history.at(-1), node=model.nodes.get(id), outgoing=model.outgoing.get(id), choices=$('guide-choices');
    $('guide-position').textContent='Lượt '+history.length+' · Dẫn qua luồng';
    $('guide-title').textContent=node.title;$('guide-summary').textContent=node.summary;
    choices.replaceChildren();$('guide-back').disabled=history.length===1;
    for(const edge of outgoing)branch(choices,edge,()=>{history.push(edge.to);renderGuide(true);});
    if(!outgoing.length)button(choices,'Kết thúc hướng dẫn',()=>closeGuide(true),'primary');
    inspect(id,{guided:true});
    if(focusChoice)choices.querySelector('button')?.focus({preventScroll:true});
  }
  function startGuide(){closeSearch();setMode('technical');history=[graph.entry_node];$('guide').hidden=false;renderGuide(true);}
  function closeGuide(restore){
    if($('guide').hidden)return;
    $('guide').hidden=true;history=[];if(restore)$('guide-start').focus();
  }
  $('guide-start').onclick=startGuide;$('guide-close').onclick=()=>closeGuide(true);
  $('guide-back').onclick=()=>{if(history.length>1){history.pop();renderGuide(true);}};
  document.addEventListener('keydown',ev=>{
    if(ev.key==='Escape'){
      if(!results.hidden){search.focus();closeSearch();}
      else if(!$('guide').hidden)closeGuide(true);
      return;
    }
    if(ev.key==='/'&&!ev.ctrlKey&&!ev.metaKey&&!ev.altKey&&!ev.target.closest('input,textarea,select,[contenteditable]')){ev.preventDefault();search.focus();}
  });
  const themeOptions=['system','light','dark'];let theme='system';
  try{const prior=localStorage.getItem('pfe-theme');if(themeOptions.includes(prior))theme=prior;}catch{}
  function applyTheme(){
    const text={system:'Theo thiết bị',light:'Sáng',dark:'Tối'}[theme];
    document.documentElement.dataset.theme=theme==='system'?(systemTheme.matches?'dark':'light'):theme;
    $('theme-toggle').setAttribute('aria-label','Giao diện: '+text+'. Đổi giao diện');$('theme-toggle').title='Giao diện: '+text;
  }
  $('theme-toggle').onclick=()=>{theme=themeOptions[(themeOptions.indexOf(theme)+1)%themeOptions.length];try{localStorage.setItem('pfe-theme',theme);}catch{}applyTheme();};
  systemTheme.addEventListener('change',applyTheme);applyTheme();
  $('download-flow').onclick=()=>{
    const url=URL.createObjectURL(new Blob([originalDocument],{type:'text/html;charset=utf-8'}));
    const link=element('a');link.href=url;link.download=graph.flow_id+'.html';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
  };
  $('panel-toggle').onclick=()=>setPanel($('inspector').hidden);
  $('view-technical').onclick=()=>setMode('technical');$('view-simple').onclick=()=>setMode('simple');
  $('zoom-in').onclick=()=>canvas.zoom(1.2);$('zoom-out').onclick=()=>canvas.zoom(1/1.2);
  $('fit').onclick=()=>canvas.fit();
  for(const name of ['overview','details','evidence'])$('tab-'+name).onclick=()=>openTab(name);
  window.addEventListener('resize',()=>{if(mode==='technical'){if(selected)canvas.reveal(selected);else canvas.fit();}});
  if(small.matches)canvas.reveal(graph.entry_node);
  openTab('overview');
})();
