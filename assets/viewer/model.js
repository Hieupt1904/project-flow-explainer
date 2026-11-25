/* Data-only projections shared by the map, search and evidence views. */
const FlowModel = (() => {
  const confidence = Object.freeze({
    verified:'Có căn cứ tĩnh', partial:'Căn cứ một phần', inferred:'Suy luận',
    unknown:'Chưa xác minh', illustrative:'Minh họa',
  });
  const types = Object.freeze({
    start:'Bắt đầu', message:'Thông báo', action:'Hành động', decision:'Điều kiện',
    data:'Dữ liệu', end:'Kết thúc', error:'Nhánh lỗi', external:'Hệ thống ngoài',
  });
  const edgeKinds = Object.freeze({normal:'Tiếp tục', condition:'Điều kiện', success:'Nhánh thành công', error:'Nhánh lỗi', fallback:'Phương án dự phòng', loop:'Vòng lặp'});
  const evidence = new Map(Object.entries({entry:'Khai báo điểm vào', import:'Nhập mô-đun',
    call:'Vị trí gọi hàm', structure:'Cấu trúc mã nguồn', condition:'Điều kiện trong mã nguồn',
    error:'Nhánh lỗi trong mã nguồn', error_site:'Vị trí báo lỗi', branch:'Nhánh trong mã nguồn'}));
  function fold(text) {
    return String(text ?? '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/đ/g, 'd').trim();
  }
  function locationOf(ref) {
    const start = ref.start_line;
    const end = ref.end_line;
    return ref.path + (start ? ':' + start + (end > start ? '–' + end : '') : '');
  }
  function edgeEvidence(value) { return evidence.get(value) ?? 'Chưa nêu căn cứ'; }

  function createModel(graph) {
    const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
    const outgoing = new Map(graph.nodes.map(({id}) => [id, []]));
    const incoming = new Map(graph.nodes.map(({id}) => [id, []]));
    const confidenceCounts = new Map(Object.keys(confidence).map((key) => [key, 0]));
    const sourceMap = new Map();
    const index = new Map();
    for (const edge of graph.edges) {
      outgoing.get(edge.from).push(edge);
      incoming.get(edge.to).push(edge);
    }
    for (const node of graph.nodes) {
      confidenceCounts.set(node.confidence, confidenceCounts.get(node.confidence) + 1);
      const refs = [];
      for (const ref of node.source_refs ?? []) {
        const location = locationOf(ref);
        const key = JSON.stringify([ref.path, ref.start_line ?? null, ref.end_line ?? ref.start_line ?? null]);
        if (!sourceMap.has(key)) sourceMap.set(key, {location, path:ref.path, nodes:[], symbols:new Set()});
        const source = sourceMap.get(key);
        if (source.nodes.at(-1) !== node) source.nodes.push(node);
        if (ref.symbol) source.symbols.add(ref.symbol);
        refs.push(location, ref.symbol);
      }
      index.set(node.id, fold([node.id, node.title, node.summary, node.details, node.technical,
        node.actor, types[node.type], confidence[node.confidence], ...refs,
        ...outgoing.get(node.id).flatMap((edge) => [edge.label, edge.technical])].join(' ')));
    }
    // Cache one shortest route per node. Prefer acyclic links, but accept a loop
    // as the only way to reach a step in a hand-authored graph.
    const paths = new Map([[graph.entry_node, null]]);
    const order = [graph.entry_node];
    const deferred = [];
    function discover(edge) {
      if (!paths.has(edge.to)) {
        paths.set(edge.to, edge);
        order.push(edge.to);
      }
    }
    let cursor = 0;
    for (let loopIndex = 0; ; loopIndex++) {
      while (cursor < order.length) {
        for (const edge of outgoing.get(order[cursor++])) {
          if (edge.kind === 'loop') deferred.push(edge);
          else discover(edge);
        }
      }
      if (loopIndex === deferred.length) break;
      discover(deferred[loopIndex]);
    }
    function pathTo(target) {
      if (!paths.has(target)) return null;
      const route = [];
      for (let edge = paths.get(target); edge; edge = paths.get(edge.from)) route.push(edge);
      return route.reverse();
    }
    function search(query, level = '') {
      const words = fold(query).split(/\s+/).filter(Boolean);
      return order.map((id) => nodes.get(id)).filter((node) =>
        (!level || node.confidence === level) && words.every((word) => index.get(node.id).includes(word)));
    }
    return {nodes, outgoing, incoming, confidenceCounts, order, search, pathTo,
      sources:[...sourceMap.values()].sort((a,b) => a.location.localeCompare(b.location, 'vi', {numeric:true}))};
  }
  return {createModel, fold, locationOf, confidence, types, edgeKinds, edgeEvidence};
})();
