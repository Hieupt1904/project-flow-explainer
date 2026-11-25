/* DOM helpers. All graph values enter the DOM as text. */
const byId=id=>document.getElementById(id);
function element(tag,cls,text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=String(text);return node;}
function add(root,tag,cls,text){const node=element(tag,cls,text);root.append(node);return node;}
function svg(tag,attrs={}){const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,v] of Object.entries(attrs))node.setAttribute(key,v);return node;}
const iconPaths={
  flow:'M2 12h5l4-5h10M7 12l4 5h10 M18 4l3 3-3 3 M18 14l3 3-3 3',
  map:'M3 5h18v14H3z M8 5l2 14m6-14-2 14',list:'M6 6h14M6 12h14M6 18h14M3 6h.1M3 12h.1M3 18h.1',
  search:'M16 10a6 6 0 1 1-12 0 6 6 0 0 1 12 0zm-2 4 5 5',compass:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z M16 8l-2 6-6 2 2-6z',
  theme:'M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM12 4v16',download:'M12 3v12m-5-5 5 5 5-5M4 20h16',
  panel:'M3 4h18v16H3z M15 4v16',close:'m6 6 12 12M18 6 6 18',back:'m15 6-6 6 6 6',
  minus:'M5 12h14',plus:'M12 5v14M5 12h14',fit:'M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5',
  start:'M7 4v16l12-8z',message:'M4 5h16v11H8l-4 3z',action:'M5 19 19 5m0 0h-7m7 0v7',decision:'m12 3 8 9-8 9-8-9z',
  data:'M5 5a7 3 0 1 0 14 0A7 3 0 1 0 5 5v14a7 3 0 0 0 14 0V5M5 12a7 3 0 0 0 14 0',
  end:'M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0z M8 12l3 3 5-6',
  error:'M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0z M12 8v5m0 3h.01',external:'M14 4h6v6m0-6-8 8m-8-6h6m-6 0v12h12v-6',
};
function icon(name){
  const node=svg('svg',{class:'icon',viewBox:'0 0 24 24','aria-hidden':'true',fill:'none',stroke:'currentColor','stroke-width':1.7,'stroke-linecap':'round','stroke-linejoin':'round'});
  node.append(svg('path',{d:iconPaths[name]}));return node;
}
function button(root,text,action,cls='secondary'){
  const node=add(root,'button',cls,text);node.type='button';node.onclick=action;return node;
}
function badge(root,level){return add(root,'span','label '+level,FlowModel.confidence[level]);}
