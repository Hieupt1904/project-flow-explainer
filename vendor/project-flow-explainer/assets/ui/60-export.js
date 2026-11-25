// Export: a copy of the map to share as one HTML file, for people without Claude or Codex. The map's server
// (serve.mjs) builds it: the same page without the Ask bar, requests for Claude or Codex, or links into this
// computer, plus the extras ticked here. Talks to the viewer only through window.ProjectFlow.
(() => {
  const SC = window.ProjectFlow;
  if (!SC || SC.exported || SC.graph.pfeFlow) return;
  const S = window.PROJECT_FLOW_SERVER;
  // opened in the Claude app: there's no map folder to export from
  if (!S && location.protocol !== 'file:') return;
  const { h } = SC;
  const G = SC.graph;
  const PLAN = !!G.meta.blueprint;
  const CMD = 'node project-flow-explainer/serve.mjs --export';

  const style = document.createElement('style');
  style.textContent = `
.xp-opts { display: flex; flex-direction: column; gap: 2px; margin: 14px 0 4px; }
.xp-opt { display: flex; gap: 12px; align-items: flex-start; padding: 10px 12px; border-radius: 12px; cursor: pointer; }
.xp-opt:hover { background: rgba(var(--ink), .05); }
.xp-opt input { margin: 3px 0 0; width: 16px; height: 16px; accent-color: var(--accent); flex: none; cursor: pointer; }
.xp-opt b { display: block; font-weight: 500; color: var(--text); }
.xp-opt span { display: block; font-size: 12.5px; color: var(--text-3); line-height: 1.5; }
.xp-opt.warn span { color: var(--warn-text); }
.xp-note { font-size: 12.5px; color: var(--text-3); line-height: 1.55; margin-top: 10px; }
.xp-err { font-size: 12.5px; color: var(--warn-text); background: var(--warn-bg); border-radius: 10px; padding: 8px 12px; margin-top: 10px; }
`;
  document.head.appendChild(style);
  SC.icons.export = '<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5"/><path d="M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4"/>';

  // only what this map has; the extras that say how the app could be attacked are off unless ticked
  const PARTS = [
    { id: 'flows', label: 'Luồng và tour', hint: 'Các luồng dẫn từng bước, gồm cả luồng do bạn yêu cầu.', on: true, has: G.flows.length > 0 || (G.tour || []).length > 0 },
    { id: 'notes', label: 'Ghi chú ghim vào tệp', hint: 'Các ghi chú hiện trên thẻ tệp.', on: true, has: G.files.some((f) => f.note) },
    { id: 'recent', label: 'Việc gần đây', hint: 'Những gì vừa thay đổi và lý do.', on: false, has: !!G.recent?.items?.length },
    PLAN
      ? { id: 'health', label: 'Rà soát thiết kế', hint: 'Các quyết định mà kế hoạch vẫn còn bỏ ngỏ.', on: false, has: !!G.health?.issues?.length }
      : { id: 'health', label: 'Kiểm tra sức khỏe', hint: 'Liệt kê các endpoint ai cũng dùng được và vị trí bí mật trong mã (không kèm giá trị). Chỉ đưa vào cho người bạn tin tưởng.', on: false, warn: true, has: !!G.health?.issues?.length },
  ].filter((p) => p.has);

  async function download(el, close) {
    const err = el.querySelector('.xp-err');
    const include = [...el.querySelectorAll('[data-xp]')].filter((c) => c.checked).map((c) => c.dataset.xp);
    // flows requested since the map was last built live only on this page so far
    const flows = G.flows.filter((f) => f.custom).map((f) => ({ id: f.id, title: f.title, description: f.description, steps: f.steps }));
    try {
      const r = await fetch('/api/export', { method: 'POST', headers: { 'content-type': 'application/json', 'x-project-flow-explainer-token': S.token }, body: JSON.stringify({ include, flows }) });
      if (r.status === 403) throw new Error('Máy chủ của sơ đồ đã khởi động lại sau khi trang này mở. Hãy tải lại trang rồi thử lại.');
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'Máy chủ của sơ đồ không xuất được tệp.');
      const name = /filename="([^"]+)"/.exec(r.headers.get('content-disposition') || '')?.[1] || 'project-flow-explainer-map.html';
      const a = document.createElement('a');
      a.href = URL.createObjectURL(await r.blob());
      a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 30000);
      close();
      SC.toast(`Đã tải xuống ${name}`);
    } catch (e) {
      err.hidden = false;
      err.textContent = e.message === 'Failed to fetch' ? 'Không kết nối được máy chủ của sơ đồ. Hãy khởi động lại máy chủ rồi thử lại.' : e.message;
    }
  }

  function openExport() {
    if (!S) {
      SC.modal({
        title: 'Xuất bản sao',
        html: `<p>Để xuất bản chia sẻ từ tệp HTML, chạy lệnh sau trong thư mục gốc của kho mã:</p><pre>${h(CMD)}</pre>`,
        actions: [{ label: 'Sao chép lệnh', primary: true, icon: 'copy', onClick: () => { SC.copy(CMD).then((ok) => { if (ok) SC.toast('Đã sao chép'); }); } }],
      });
      return;
    }
    const m = SC.modal({
      title: 'Xuất bản sao',
      html: `<p>Một tệp HTML chứa toàn bộ sơ đồ, gửi được cho bất kỳ ai. Tệp mở trong mọi trình duyệt, không cần cài gì và không có thanh Ask.</p>
        ${PARTS.length ? `<div class="xp-opts">${PARTS.map((p) => `<label class="xp-opt${p.warn ? ' warn' : ''}"><input type="checkbox" data-xp="${p.id}"${p.on ? ' checked' : ''}><div><b>${h(p.label)}</b><span>${h(p.hint)}</span></div></label>`).join('')}</div>` : ''}
        <p class="xp-note">Tệp cho thấy ${h(G.project.name)} được ghép thế nào: từng phần, tệp và endpoint, cùng tên các hàm bên trong, nhưng không có mã nguồn.</p>
        <div class="xp-err" hidden></div>`,
      actions: [{ label: 'Tải xuống', primary: true, icon: 'export', keepOpen: true, onClick: (close) => { download(m.el, close); } }],
    });
  }

  SC.addHeaderButton({ id: 'btn-export', label: 'Xuất', icon: 'export', title: 'Xuất bản sao của sơ đồ này để chia sẻ', onClick: openExport });
})();
