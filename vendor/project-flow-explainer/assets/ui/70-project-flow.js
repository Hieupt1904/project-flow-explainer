(()=>{
  const SC=window.ProjectFlow;if(!SC||!SC.graph.pfeFlow)return;const G=SC.graph, h=SC.h;
  const flow=G.pfeFlow, nodes=new Map(flow.nodes.map(n=>[n.id,n])), byRef=new Map(flow.nodes.map(n=>['n:step-'+n.id,n]));
  const levels={verified:'Có căn cứ tĩnh',partial:'Căn cứ một phần',inferred:'Suy luận',unknown:'Chưa xác minh',illustrative:'Minh họa'};
  const pathFor=ref=>ref.path+(ref.start_line?':'+ref.start_line+(ref.end_line>ref.start_line?'–'+ref.end_line:''):'');
  const refs=node=>(node.source_refs||[]).map(ref=>'<div class="row"><span class="rt"><code class="rp">'+h(pathFor(ref))+'</code>'+(ref.symbol?'<div class="rd"><code>'+h(ref.symbol)+'</code></div>':'')+'</span></div>').join('');
  let history=[];
  async function guide(id,focus=false){
    const node=nodes.get(id);if(!node)return;
    const branches=flow.edges.filter(e=>e.from===id);
    await SC.reveal('n:step-'+id);
    if(history.at(-1)!==id)return;
    SC.showPanel('<div class="sec"><div class="kindlabel">Dẫn qua luồng · Lượt '+history.length+'</div><h2 class="pt">'+h(node.title)+'</h2><p class="pd">'+h(node.summary)+'</p><div class="callout">'+h(levels[node.confidence])+'</div></div>'+
      '<div class="sec"><h3>Đi tiếp khi nào?</h3><div class="list">'+(branches.length?branches.map((e,i)=>'<button class="btn soft" type="button" data-pfe-branch="'+i+'">'+h(e.label||nodes.get(e.to).title)+(e.kind==='loop'?' · Lặp lại':'')+'</button>').join(''):'<p class="pd">Sơ đồ kết thúc tại bước này.</p>')+'</div><div class="actions">'+(history.length>1?'<button class="btn soft" type="button" data-pfe-back>Quay lại</button>':'')+'<button class="btn soft" type="button" data-pfe-close>'+ (branches.length?'Đóng hướng dẫn':'Kết thúc hướng dẫn') +'</button></div></div>'+
      '<div class="sec"><h3>Căn cứ trong mã nguồn</h3>'+(refs(node)||'<p class="pd">Bước này chưa có vị trí mã nguồn.</p>')+'</div>',panel=>{
        panel.querySelectorAll('[data-pfe-branch]').forEach(button=>button.onclick=()=>{const edge=branches[Number(button.dataset.pfeBranch)];history.push(edge.to);guide(edge.to,true);});
        const back=panel.querySelector('[data-pfe-back]');if(back)back.onclick=()=>{history.pop();guide(history.at(-1),true);};
        panel.querySelector('[data-pfe-close]').onclick=()=>{history=[];SC.closePanel();document.getElementById('pfe-guide')?.focus();};
        if(focus)panel.querySelector('[data-pfe-branch], [data-pfe-close]')?.focus({preventScroll:true});
    });
  }
  SC.addPanelSection('item',item=>{
    const node=byRef.get(item);if(!node)return null;
    const edges=flow.edges.filter(e=>e.from===node.id);
    return {html:'<div class="sec"><h3>Căn cứ trong mã nguồn</h3><p class="pd">'+h(levels[node.confidence])+'</p>'+(refs(node)||'<p class="pd">Chưa có vị trí mã nguồn.</p>')+'</div>'+
      (edges.length?'<div class="sec"><h3>Các nhánh</h3><div class="list">'+edges.map(e=>'<a class="row" data-go="n:step-'+h(e.to)+'"><span class="rt"><div class="rn">'+h(e.label||nodes.get(e.to).title)+'</div><div class="rd">'+h(nodes.get(e.to).title)+'</div></span></a>').join('')+'</div></div>':'')};
  });
  SC.addPanelSection('overview',()=>({top:true,html:'<div class="sec"><h3>Phạm vi sơ đồ</h3><p class="pd">'+h(flow.nodes.every(n=>n.confidence==='illustrative')?'Đây là luồng minh họa, không phải kết quả đọc mã nguồn.':'Đây là phân tích tĩnh của một luồng cụ thể, không phải bản đồ toàn kho.')+'</p></div>'}));
  SC.addHeaderButton({id:'pfe-guide',label:'Dẫn qua luồng',icon:'route',onClick:()=>{history=[flow.entry_node];guide(flow.entry_node,true);}});
  SC.addHeaderButton({id:'pfe-evidence',label:'Căn cứ',icon:'search',onClick:()=>{
    const source=flow.nodes.filter(n=>n.source_refs?.length);
    SC.showPanel('<div class="sec"><h2 class="pt">Căn cứ và giới hạn</h2><p class="pd">Căn cứ tĩnh không xác nhận hành vi khi chạy.</p></div>'+source.map(n=>'<div class="sec"><h3>'+h(n.title)+'</h3>'+refs(n)+'</div>').join('')+(flow.assumptions||[]).map(a=>'<div class="sec"><p class="pd">'+h(a)+'</p></div>').join(''));
  }});
  SC.addHeaderButton({id:'pfe-sharing',label:'Tải HTML',icon:'export',onClick:()=>{
    const anchor=document.createElement('a');anchor.href=location.href.split('#')[0];anchor.download=flow.flow_id+'.html';anchor.click();
  }});
})();
