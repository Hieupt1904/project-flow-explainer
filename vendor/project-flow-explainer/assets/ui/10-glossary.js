// project-flow-explainer glossary: explains the technical words a non-developer meets on the map.
// The first time a known term appears in a description (details panel, board title area), it gets a
// dotted underline; hovering or focusing it shows a one-sentence explanation. Off while
// "Hiện chi tiết kỹ thuật" is on. Talks to the viewer only through window.ProjectFlow.
(() => {
  const SC = window.ProjectFlow;
  if (!SC) return;

  // [display name, plain explanation, aliases...]. Aliases are matched as whole words, ignoring case,
  // except those marked with a leading "=" (matched exactly, so "REST" doesn't fire on "the rest").
  const TERMS = [
    ['API', 'Cách các chương trình nói chuyện với nhau: một bên hỏi (giá cả, một đơn hàng), bên kia trả lời.', 'API', 'APIs', 'API client'],
    ['Endpoint', 'Một yêu cầu cụ thể mà ứng dụng nhận được, như "đánh dấu đơn này đã gửi"; mỗi endpoint có địa chỉ web riêng.', 'endpoint', 'endpoints'],
    ['Webhook', 'Tin nhắn một dịch vụ khác tự gửi cho ứng dụng khi có sự kiện xảy ra ở đó, như "một khoản thanh toán đã xong".', 'webhook', 'webhooks'],
    ['Server', 'Máy chủ trên đám mây chạy phần việc ngầm của ứng dụng và trả lời yêu cầu từ các màn hình.', 'server', 'servers', 'main server'],
    ['Frontend', 'Phần ứng dụng mà người dùng nhìn thấy và bấm: màn hình, nút và biểu mẫu trong trình duyệt.', 'frontend', 'front end', 'front-end'],
    ['Backend', 'Phần ngầm của ứng dụng: lưu bản ghi, áp quy tắc và trao đổi với các dịch vụ khác.', 'backend', 'back end', 'back-end'],
    ['Database', 'Nơi ứng dụng lưu bản ghi (sản phẩm, đơn hàng, khách hàng) để không mất dữ liệu khi khởi động lại.', 'database', 'databases', 'DB'],
    ['Record', 'Một mục đã lưu trong cơ sở dữ liệu, như một đơn hàng hay một khách hàng; bảng là danh sách mọi bản ghi cùng loại.', 'database record', 'database records', 'database table', 'database tables'],
    ['Model', 'Trong mã nguồn, model mô tả cách một loại bản ghi (đơn hàng, khách hàng) được lưu trong cơ sở dữ liệu.', 'model', 'models', 'ORM', 'ORM model', 'ORM models', 'data model'],
    ['Query', 'Câu hỏi ứng dụng gửi cho cơ sở dữ liệu, như "mọi đơn hàng hôm nay chưa gửi".', 'query', 'queries'],
    ['Queue', 'Hàng đợi việc: công việc được đưa vào và xử lý lần lượt ở chế độ ngầm để không mất.', 'queue', 'queues', 'queued', 'outbox', 'message queue'],
    ['Background job', 'Việc tự chạy ngầm để người dùng không phải chờ trên màn hình.', 'background job', 'background jobs', 'background task', 'background tasks', 'worker', 'workers'],
    ['Scheduled job', 'Việc tự chạy theo lịch, như mỗi giờ hoặc mỗi đêm.', 'cron', 'cron job', 'cron jobs', 'scheduled job', 'scheduled jobs', 'scheduler'],
    ['Environment variable', 'Cài đặt lưu ngoài mã nguồn, như dùng cơ sở dữ liệu hay tài khoản nào, để khác nhau giữa thử nghiệm và chạy thật.', 'environment variable', 'environment variables', 'env var', 'env vars', '.env'],
    ['Secret', 'Mật khẩu hoặc khóa ứng dụng dùng để đăng nhập dịch vụ khác; không bao giờ chia sẻ hay đưa vào mã nguồn.', 'secret', 'secrets', 'API key', 'API keys', 'credentials'],
    ['Deploy', 'Đưa phiên bản mới của ứng dụng lên chạy thật để người dùng bắt đầu sử dụng.', 'deploy', 'deploys', 'deployed', 'deployment', 'deployments'],
    ['Migration', 'Thay đổi một lần cách lưu bản ghi, như thêm trường mới cho mọi đơn hàng.', 'migration', 'migrations'],
    ['Cache', 'Bản sao đã lưu của một thứ gì đó, giữ gần để tải nhanh hơn thay vì tính lại.', 'cache', 'cached', 'caching'],
    ['Sign-in', 'Kiểm tra người dùng là ai (thường bằng mật khẩu) trước khi cho vào.', 'auth', 'authentication', 'login', 'log in', 'sign-in', 'sign in'],
    ['Permissions', 'Quy tắc ai được làm gì, như chỉ quản lý mới được hoàn tiền.', 'permissions', 'authorization', 'roles', 'RBAC'],
    ['Session', 'Cách ứng dụng nhớ bạn đã đăng nhập, để bạn không phải nhập mật khẩu ở mỗi màn hình.', 'session', 'sessions'],
    ['Token', 'Vé điện tử tạm thời ứng dụng cấp sau khi đăng nhập và kiểm tra ở mỗi yêu cầu.', 'token', 'tokens', 'bearer token', 'access token'],
    ['SDK', 'Bộ mã nguồn dựng sẵn do một công ty cung cấp để ứng dụng dễ nói chuyện với dịch vụ của họ.', 'SDK', 'SDKs'],
    ['Repository', 'Thư mục chứa toàn bộ mã nguồn của dự án và toàn bộ lịch sử thay đổi.', 'repository', 'repositories', 'repo', 'repos'],
    ['Component', 'Khối dựng sẵn dùng lại được của màn hình, như một nút, một bảng hay cả trình sửa sản phẩm.', 'component', 'components'],
    ['Route', 'Địa chỉ web ứng dụng trả lời: trên màn hình là một trang, trên server là một loại yêu cầu.', 'route', 'routes', 'routing', 'App Router'],
    ['Request', 'Tin nhắn yêu cầu server làm hoặc lấy gì đó; server gửi lại phản hồi kèm kết quả.', 'request', 'requests', 'response', 'responses'],
    ['JSON', 'Định dạng văn bản đơn giản để chương trình gửi dữ liệu cho nhau, như một danh sách có nhãn.', 'JSON'],
    ['REST', 'Cách phổ biến để xây API: mỗi địa chỉ web ứng với một loại thứ (đơn hàng, sản phẩm).', '=REST', '=RESTful'],
    ['HTTP method', 'Loại yêu cầu: GET đọc, POST tạo, PUT hoặc PATCH sửa, DELETE xóa.', 'HTTP method', 'HTTP methods', '=GET', '=POST', '=PUT', '=PATCH', '=DELETE'],
    ['HTTP', 'Ngôn ngữ trình duyệt và server dùng để nói chuyện trên web; HTTPS là bản mã hóa.', 'HTTP', 'HTTPS'],
    ['CDN', 'Mạng server khắp thế giới giao ảnh và tệp nhanh từ nơi gần người truy cập.', 'CDN', 'CDNs'],
    ['Storage bucket', 'Kho tệp trên đám mây cho ảnh sản phẩm, tệp tải lên và bản xuất.', 'storage bucket', 'bucket', 'buckets', 'S3', 'GCS', 'Cloud Storage'],
    ['Pub/Sub', 'Dịch vụ tin nhắn của Google: một phần ứng dụng đăng sự kiện, phần khác nhận và xử lý ngầm.', 'Pub/Sub', 'PubSub'],
    ['MCP', 'Cách chuẩn để nối trợ lý AI (như Claude hay ChatGPT) với ứng dụng để chúng tra cứu thông tin.', 'MCP', 'MCP server', 'Model Context Protocol'],
    ['Next.js', 'Bộ công cụ phổ biến để xây trang web và ứng dụng web bằng React.', 'Next.js', 'NextJS'],
    ['React', 'Thư viện phổ biến để xây màn hình tương tác từ các khối dùng lại được.', '=React'],
    ['Flask', 'Bộ công cụ Python để xây server web.', 'Flask'],
    ['SQLAlchemy', 'Bộ công cụ Python giúp mã nguồn đọc và lưu bản ghi mà không cần viết lệnh cơ sở dữ liệu thô.', 'SQLAlchemy'],
    ['Postgres', 'Cơ sở dữ liệu phổ biến; RDS và Cloud SQL là bản chạy trên đám mây của Amazon và Google.', 'Postgres', 'PostgreSQL', 'RDS', 'Cloud SQL'],
    ['Docker', 'Cách đóng gói ứng dụng cùng mọi thứ nó cần để chạy giống nhau trên mọi máy hoặc đám mây.', 'Docker', 'container', 'containers'],
    ['Cloud Run', 'Dịch vụ của Google chạy server và việc ngầm của ứng dụng trên đám mây, không cần quản máy.', 'Cloud Run'],
    ['Middleware', 'Bước kiểm tra mọi yêu cầu đi qua trên đường vào, như "người này đã đăng nhập chưa?".', 'middleware'],
    ['Blueprint', 'Trong Flask, một nhóm yêu cầu liên quan gói lại, như toàn bộ yêu cầu về đơn hàng.', 'blueprint', 'blueprints'],
    ['Tests', 'Kiểm tra tự động xem mã nguồn còn làm đúng việc không, chạy trước khi thay đổi lên thật.', 'test suite', 'unit test', 'unit tests', 'pytest', 'Vitest'],
    ['Script', 'Chương trình nhỏ chạy tay cho một việc một lần, như sửa hoặc nhập dữ liệu.', 'script', 'scripts'],
    ['OAuth', 'Chuẩn đứng sau nút "Đăng nhập bằng…": cho một ứng dụng dùng ứng dụng khác thay bạn mà không chia sẻ mật khẩu.', 'OAuth'],
  ];

  const exact = new Map(), loose = new Map(), alts = [];
  TERMS.forEach(([name, text, ...aliases], i) => {
    for (let a of aliases) {
      const strict = a.startsWith('=');
      if (strict) a = a.slice(1);
      (strict ? exact : loose).set(strict ? a : a.toLowerCase(), i);
      alts.push(a);
    }
  });
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  alts.sort((a, b) => b.length - a.length);
  const RE = new RegExp(`(?<![\\w./-])(?:${alts.map(esc).join('|')})(?![\\w/]|-\\w|\\.\\w)`, 'gi');
  const termOf = (m) => exact.has(m) ? exact.get(m) : loose.has(m.toLowerCase()) ? loose.get(m.toLowerCase()) : -1;

  // Where to look, and what to leave alone.
  const TARGETS = '.pd, .rd, .callout';
  const SKIP = 'a[href], button, code, pre, kbd, samp, input, textarea, select, [contenteditable], .tag, .rp, .pp, .method, .kbd, .sc-term, [data-noglossary]';
  const CLICKABLE = 'a, [data-go], [data-sel], [data-flow], [data-open], [role="button"]';
  const isMono = (el) => /mono|monospace/i.test(el.style?.fontFamily || '');

  function annotate(scope, targets) {
    if (!scope || SC.technical()) return;
    const used = new Set([...scope.querySelectorAll('.sc-term')].map((s) => +s.dataset.term)); // max one per term per scope
    const skipped = (from, stop) => { for (let p = from; p && p !== stop; p = p.parentElement) if (p.matches(SKIP) || isMono(p)) return true; return false; };
    for (const el of targets) {
      if (skipped(el, scope)) continue;
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
        acceptNode: (t) => !t.nodeValue.trim() || skipped(t.parentElement, el) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
      });
      const texts = [];
      while (walker.nextNode()) texts.push(walker.currentNode);
      for (const t of texts) wrapIn(t, used);
    }
  }
  function wrapIn(textNode, used) {
    let node = textNode;
    while (node) {
      RE.lastIndex = 0;
      let m, hit = null;
      while ((m = RE.exec(node.nodeValue))) {
        const i = termOf(m[0]);
        if (i >= 0 && !used.has(i)) { hit = { m, i }; break; }
      }
      if (!hit) return;
      used.add(hit.i);
      const word = node.splitText(hit.m.index);
      const rest = word.splitText(hit.m[0].length);
      const span = document.createElement('span');
      span.className = 'sc-term';
      span.dataset.term = String(hit.i);
      if (!word.parentElement.closest(CLICKABLE)) span.tabIndex = 0; // inside clickable rows: hover only, clicks pass through
      word.replaceWith(span);
      span.appendChild(word);
      node = rest;
    }
  }
  function strip(scope) {
    if (!scope) return;
    for (const s of scope.querySelectorAll('.sc-term')) s.replaceWith(...s.childNodes);
    scope.normalize();
  }

  const panelEl = () => document.getElementById('panel');
  const contextEl = () => document.getElementById('context');
  const doPanel = () => { const p = panelEl(); if (p) annotate(p, p.querySelectorAll(TARGETS)); };
  const doContext = () => { const c = contextEl(); if (c) annotate(c, c.querySelectorAll('p, .callout')); };

  // Run after the viewer and any other extension listeners have finished filling the DOM.
  SC.on('panel', () => { hide(true); queueMicrotask(doPanel); });
  SC.on('render', () => { hide(true); queueMicrotask(doContext); });
  SC.on('technical', (on) => {
    hide(true);
    if (on) { strip(panelEl()); strip(contextEl()); }
    else { queueMicrotask(() => { strip(panelEl()); strip(contextEl()); doPanel(); doContext(); }); }
  });

  // ---------- popover ----------
  const style = document.createElement('style');
  style.textContent = `
.sc-term { pointer-events: auto; cursor: help; border-radius: 4px; text-decoration-line: underline; text-decoration-style: dotted; text-decoration-thickness: 1px; text-underline-offset: 3px;
  text-decoration-color: rgba(var(--ink), .32); text-decoration-color: color-mix(in srgb, currentColor 45%, transparent); transition: text-decoration-color .2s var(--ease), color .2s var(--ease); }
.sc-term:hover, .sc-term.on { text-decoration-color: currentColor; color: var(--text); }
.callout .sc-term:hover, .callout .sc-term.on { color: inherit; }
.sc-term:focus { outline: none; }
.sc-term:focus-visible { box-shadow: 0 0 0 2px var(--focus); }
#sc-gloss { position: fixed; left: 0; top: 0; z-index: 55; max-width: 280px; padding: 11px 13px; border-radius: 14px; font-size: 12.5px; line-height: 1.5; color: var(--text-2);
  pointer-events: none; opacity: 0; transform: translateY(3px); transition: opacity .15s var(--ease), transform .25s var(--ease); }
#sc-gloss.on { opacity: 1; transform: none; }
#sc-gloss b { display: block; color: var(--text); font-weight: 600; margin-bottom: 2px; }`;
  document.head.appendChild(style);

  const pop = document.createElement('div');
  pop.id = 'sc-gloss';
  pop.className = 'glass';
  pop.setAttribute('role', 'tooltip');
  document.body.appendChild(pop);

  let current = null, showT = 0, hideT = 0;
  function show(el) {
    clearTimeout(hideT);
    if (current === el) return;
    const term = TERMS[+el.dataset.term];
    if (!term) return;
    current?.classList.remove('on'); current?.removeAttribute('aria-describedby');
    current = el;
    el.classList.add('on');
    el.setAttribute('aria-describedby', 'sc-gloss');
    pop.innerHTML = `<b>${SC.h(term[0])}</b>${SC.h(term[1])}`;
    const r = el.getClientRects()[0] || el.getBoundingClientRect();
    const pw = pop.offsetWidth, ph = pop.offsetHeight, gap = 8;
    const x = Math.max(12, Math.min(r.left, innerWidth - pw - 12));
    const below = r.bottom + gap + ph <= innerHeight - 12;
    const y = below ? r.bottom + gap : Math.max(12, r.top - gap - ph);
    pop.style.left = `${Math.round(x)}px`;
    pop.style.top = `${Math.round(y)}px`;
    pop.classList.add('on');
  }
  function hide(now) {
    clearTimeout(showT); clearTimeout(hideT);
    const go = () => { pop.classList.remove('on'); current?.classList.remove('on'); current?.removeAttribute('aria-describedby'); current = null; };
    if (now === true) go(); else hideT = setTimeout(go, 90);
  }
  const termAt = (ev) => ev.target instanceof Element ? ev.target.closest('.sc-term') : null;
  document.addEventListener('mouseover', (ev) => { const t = termAt(ev); if (!t) return; clearTimeout(showT); showT = setTimeout(() => show(t), current ? 0 : 140); });
  document.addEventListener('mouseout', (ev) => { const t = termAt(ev); if (t && !t.contains(ev.relatedTarget)) { clearTimeout(showT); hide(); } });
  document.addEventListener('focusin', (ev) => { const t = termAt(ev); if (t) show(t); });
  document.addEventListener('focusout', (ev) => { if (termAt(ev)) hide(); });
  document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && current) hide(true); });
  document.addEventListener('scroll', () => { if (current) hide(true); }, true);
  addEventListener('resize', () => { if (current) hide(true); });

  // initial pass, in case the first render/panel happened before this script ran
  if (document.readyState !== 'loading') queueMicrotask(() => { doPanel(); doContext(); });
})();
