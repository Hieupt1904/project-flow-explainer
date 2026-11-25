// Nút giao diện: Tự động (theo thiết bị) -> Sáng -> Tối -> Tự động. Lựa chọn được ghi nhớ trên
// thiết bị này. Giao diện do một đoạn script nhỏ ở đầu viewer.html chọn, trước khi vẽ bất cứ thứ gì,
// nên trang không bao giờ nháy sai màu; tệp này chỉ thêm nút và giữ nút đồng bộ.
(() => {
  const SC = window.ProjectFlow;
  const T = window.projectFlowTheme;
  if (!SC || !T) return;

  const ICON = {
    auto: '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/>',
    light: '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/>',
    dark: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  };
  const NAME = { auto: 'Tự động (theo thiết bị của bạn)', light: 'Sáng', dark: 'Tối' };
  const WORD = { auto: 'Tự động', light: 'Sáng', dark: 'Tối' };
  const NEXT = { auto: 'light', light: 'dark', dark: 'auto' };

  const style = document.createElement('style');
  style.textContent = `
    /* vùng chạm 44 px; hình tròn khi rê chuột vẫn 36 px như các nút bên cạnh */
    #theme-toggle { position: relative; flex: none; width: 44px; height: 44px; padding: 0; background: none; }
    #theme-toggle::before { content: ""; position: absolute; inset: 4px; border-radius: 999px; transition: background .2s var(--ease); }
    #theme-toggle:hover { background: none; }
    #theme-toggle:hover::before { background: rgba(var(--ink), .07); }
    #theme-toggle svg { position: relative; width: 18px; height: 18px; }
    #theme-toggle:focus-visible { outline: 2px solid var(--ring); outline-offset: -3px; }
    .theme-status { position: fixed; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
    @media (prefers-reduced-motion: reduce) { #theme-toggle, #theme-toggle::before { transition: none; } #theme-toggle:active { transform: none; } }`;
  document.head.appendChild(style);

  // trình đọc màn hình đọc lên khi giao diện đổi
  const status = document.createElement('span');
  status.className = 'theme-status';
  status.setAttribute('role', 'status');
  document.body.appendChild(status);

  const btn = SC.addHeaderButton({ id: 'theme-toggle', svg: ICON.auto, onClick: () => {
    const next = NEXT[T.get()];
    T.set(next);
    status.textContent = `Giao diện đang là ${next === 'auto' ? 'Tự động, theo thiết bị của bạn' : WORD[next]}.`;
  } });

  const show = () => {
    const c = T.get();
    btn.querySelector('svg').innerHTML = ICON[c];
    const text = `Giao diện: ${NAME[c]}. Nhấn để chuyển sang ${WORD[NEXT[c]]}.`;
    btn.title = text;
    btn.setAttribute('aria-label', text);
  };
  // Enter và Space nhấn nút này; chúng không được chạy luôn phím "mở hộp đang chọn" của trang
  btn.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') ev.stopPropagation(); });
  window.addEventListener('project-flow-explainer-theme-change', show);
  show();
})();
