// Bản phác: một sơ đồ lập từ PRD hoặc từ mô tả, trước khi đã có mã nguồn (graph.meta.blueprint,
// từ scripts/plan.mjs). Thẻ có viền đứt và tên dự án có nhãn "Bản phác", phần tổng quan
// nói sơ đồ được lập từ đâu, và mọi phần dự kiến đều có "Xây phần này với Claude": một
// câu lệnh sẵn để chỉ xây phần đó, theo đúng bản phác. Chỉ nói chuyện với viewer qua window.ProjectFlow.
(() => {
  const SC = window.ProjectFlow;
  const BP = SC && SC.graph.meta.blueprint;
  if (!BP) return;
  const { h } = SC;
  const Cap = (t) => t[0].toUpperCase() + t.slice(1);
  const A = SC.agent || { name: 'Claude', app: 'Claude Code' };
  const G = SC.graph;

  document.documentElement.classList.add('blueprint');
  const style = document.createElement('style');
  style.textContent = `
    /* dự kiến, chưa xây: viền đứt trên mọi thẻ */
    html.blueprint .card:not(.connector)::after { content: ""; position: absolute; inset: 0; border-radius: inherit; border: 2.5px dashed rgba(var(--ink), .32); pointer-events: none; }
    .bp-pill { display: inline-flex; align-items: center; height: 20px; padding: 0 8px; margin-left: 8px; border-radius: 999px; font-size: 11px; font-weight: 500; letter-spacing: .02em; color: var(--text-2); border: 1px dashed rgba(var(--ink), .35); flex: none; }
    .bp-list { margin: 8px 0 0; padding-left: 18px; color: var(--text-2); font-size: 13px; line-height: 1.55; }
    .bp-list li + li { margin-top: 4px; }
  `;
  document.head.appendChild(style);

  // nhãn "Bản phác" bên cạnh tiêu đề bảng, được vẽ lại sau mỗi lần di chuyển
  const addPill = () => {
    const k = document.querySelector('#context .k');
    if (!k || k.querySelector('.bp-pill')) return;
    k.insertAdjacentHTML('beforeend', '<span class="bp-pill" title="Dự kiến, chưa xây dựng: mọi thẻ là một phần hệ thống sẽ cần.">Bản phác</span>');
  };
  SC.on('render', addPill);
  SC.on('ready', addPill);

  const ACCESS = { public: 'tất cả mọi người', 'signed-in': 'người dùng đã đăng nhập', team: 'chỉ nhóm vận hành dịch vụ', webhook: 'dịch vụ gửi yêu cầu, dịch vụ này phải chứng minh danh tính', internal: 'chỉ các dịch vụ nội bộ của chúng ta' };
  /** "cho người dùng đã đăng nhập: quản lý của địa điểm đó", hoặc câu hỏi mở khi chưa ai quyết. */
  const whoMay = (r) => !r.access ? 'ai được dùng vẫn chưa được quyết: hỏi tôi'
    : `cho ${r.access === 'signed-in' && r.who ? r.who : ACCESS[r.access] || r.access}${r.publicBecause ? `, vì ${r.publicBecause.replace(/\.$/, '')}` : ''}`;

  SC.addPanelSection('overview', () => ({
    html: `<div class="sec"><h3>Bản phác</h3>
      <p class="pd">Dự kiến${BP.source ? ` từ <b>${h(BP.source)}</b>` : ''}, chưa xây dựng. Mọi thẻ viền đứt là một phần hệ thống sẽ cần.${SC.exported ? '' : ` Chọn một thẻ rồi chọn <b>Xây phần này với ${h(A.name)}</b> để bắt đầu.`}</p>
      ${BP.stack?.length ? `<div class="tags" style="margin-top:10px">${BP.stack.map((s) => `<span class="tag">${h(s)}</span>`).join('')}</div>` : ''}
      ${BP.assumptions?.length ? `<h3 style="margin-top:14px">Giả định</h3><ul class="bp-list">${BP.assumptions.map((a) => `<li>${h(a)}</li>`).join('')}</ul>` : ''}
    </div>`,
  }));

  /** Các tệp dự kiến bên trong một mục (một phần, một thư mục hoặc một tệp). */
  const filesIn = (id) => G.files.filter((f) => id === 'f:' + f.p || SC.chain('f:' + f.p).includes(id));
  function buildPrompt(id) {
    const i = SC.info(id);
    const fl = filesIn(id);
    const paths = new Set(fl.map((f) => 'f:' + f.p));
    const eps = SC.routes.filter((r) => paths.has('f:' + r.f));
    const deps = new Map();
    for (const l of G.links) {
      if (!paths.has(l.a) || paths.has(l.b)) continue;
      const o = SC.info(l.b);
      if (o) deps.set(l.b, `${o.name}${l.b.startsWith('f:') ? ` (${l.b.slice(2)})` : ''}`);
    }
    // câu hỏi mở từ PRD có chạm tới phần này
    const inside = (x) => x === id || paths.has(x) || (x.startsWith('r:') && paths.has('f:' + SC.routes[+x.slice(2)]?.f)) || (SC.exists(x) && SC.chain(x).includes(id));
    const questions = (G.health?.issues || []).filter((q) => q.kind === 'question' && (q.items || []).some(inside)).map((q) => q.title);
    return [
      `Xây "${i.name}" theo bản phác ${G.project.name}: project-flow-explainer/plan.json và project-flow-explainer/architecture.json${BP.source ? `, dự kiến từ ${BP.source}` : ''}.`,
      i.desc ? `\nCông dụng: ${i.desc}` : '',
      BP.stack?.length ? `\nCông nghệ: ${BP.stack.join('; ')}.` : '',
      `\nTệp cần tạo:`,
      ...fl.map((f) => `- ${f.p}: ${f.name}${f.d ? `. ${f.d}` : ''}`),
      eps.length ? `\nEndpoint cần tạo (giữ nguyên phương thức, đường dẫn và người được dùng đúng như bản phác):` : '',
      ...eps.map((r) => `- ${r.m} ${r.p} (${whoMay(r)}): ${r.name}${r.d ? `. ${r.d}` : ''}`),
      deps.size ? `\nPhụ thuộc vào: ${[...deps.values()].join('; ')}.` : '',
      questions.length ? `\nCòn chưa quyết (hỏi tôi trước khi xây phần phụ thuộc vào đây):\n${questions.map((q) => `- ${q}`).join('\n')}` : '',
      `\nTrước khi viết mã, đọc các phần này của plan.json và kiểm tra xem những thứ nó phụ thuộc đã có chưa; nếu còn thiếu, báo tôi và đề xuất nên xây gì trước. Giữ nguyên đường dẫn tệp và tên trong bản phác. Nếu bản phác sai hoặc thiếu với phần này, báo tôi trước khi sửa. Xong thì chạy nó hoặc bộ kiểm thử của nó và cho tôi biết cách dùng thử.`,
    ].filter((x) => x !== '').join('\n');
  }

  SC.addPanelSection('item', (id) => {
    if (!id || typeof id !== 'string') return '';
    // một endpoint: bản phác cho ai dùng nó
    if (id.startsWith('r:')) {
      const r = SC.routes[+id.slice(2)];
      if (!r) return '';
      const text = !r.access ? `Chưa quyết định.${SC.graph.health ? ' Phần rà soát thiết kế có nêu mục này.' : ''}` : `${Cap(r.access === 'signed-in' && r.who ? r.who : ACCESS[r.access] || r.access)}.${r.publicBecause ? ` Cố ý mở công khai: ${r.publicBecause}` : ''}`;
      return `<div class="sec"><h3>Ai được dùng</h3><p class="pd">${h(text)}</p></div>`;
    }
    const i = SC.info(id);
    if (SC.exported || !i || (i.type === 'node' && i.n.kind === 'external') || !filesIn(id).length) return '';
    return {
      html: `<div class="sec"><h3>Xây phần này</h3><p class="pd">Sẵn một yêu cầu để ${h(A.app)} xây ${i.type === 'file' ? 'tệp này' : 'phần này'} đúng như bản phác mô tả.</p>
        <div class="actions"><button class="btn soft" data-bp-build>${SC.iconI('spark')}Xây phần này với ${h(A.name)}</button></div></div>`,
      bind: (el) => el.querySelector('[data-bp-build]')?.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const prompt = buildPrompt(id);
        SC.modal({
          title: `Xây phần này với ${A.name}`,
          html: `<p class="hc-hint">Sao chép yêu cầu này rồi dán vào <b>${h(A.app)}</b> đang mở trong thư mục dự án của bạn.</p><pre>${h(prompt)}</pre>`,
          actions: [{ label: 'Sao chép câu lệnh', primary: true, icon: 'copy', onClick: () => { SC.copy(prompt).then((ok) => { if (ok) SC.toast(`Đã sao chép. Dán vào ${A.app}.`); }); } }],
        });
      }),
    };
  });
})();
