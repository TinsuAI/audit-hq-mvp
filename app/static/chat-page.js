/* Trang /chat — mount toàn trang dùng chung lõi AuditChat (chat-core.js).
 * Khác sidebar: cột trái nhóm cuộc THEO DOANH NGHIỆP (header section = doanh
 * nghiệp, 30 cuộc mỗi section + "tải thêm"), URL có nghĩa /chat/{id}
 * (history.pushState) + điều hướng back/forward.
 */
(function () {
  'use strict';

  const { util } = window.AuditChat;
  const $ = (id) => document.getElementById(id);

  const PAGE_SIZE = 30;
  const MINE_KEY = 'audit_hq_chat_mine';

  let chat = null;
  let currentUser = null;
  let isAdmin = false;
  let groups = [];                 // [{company_id, company_name, count}]
  const sections = new Map();      // key → {convs, total, has_more, open}
  let companyOptions = null;       // cache /api/chat/companies

  const groupKey = (g) => (g.company_id === null ? 'none' : String(g.company_id));

  function onlyMine() {
    if (!isAdmin) return true;
    return sessionStorage.getItem(MINE_KEY) !== '0';
  }

  function searchTerm() {
    return $('chat-search').value.trim();
  }

  function pathConvId() {
    const m = window.location.pathname.match(/^\/chat\/(\d+)/);
    return m ? parseInt(m[1], 10) : null;
  }

  // ───────────── Nạp dữ liệu ─────────────

  async function loadSection(key, { append = false } = {}) {
    const state = sections.get(key) || { convs: [], total: 0, has_more: false, open: false };
    const offset = append ? state.convs.length : 0;
    const page = await util.apiListPage({
      company_id: key, q: searchTerm(), offset, limit: PAGE_SIZE, mine: onlyMine() ? 1 : 0,
    });
    state.convs = append ? state.convs.concat(page.conversations) : page.conversations;
    state.total = page.total;
    state.has_more = page.has_more;
    sections.set(key, state);
  }

  // Section mở sẵn: nhóm của cuộc đang mở (doanh nghiệp đang xem). Khi đang tìm
  // kiếm thì mở mọi nhóm có kết quả — nếu không cán bộ phải tự bấm từng section
  // để thấy cái vừa tìm ra.
  function defaultOpenKeys(activeConv) {
    if (searchTerm()) return new Set(groups.map(groupKey));
    if (activeConv) {
      return new Set([activeConv.company_id === null ? 'none' : String(activeConv.company_id)]);
    }
    return new Set(groups.length ? [groupKey(groups[0])] : []);
  }

  async function refreshList() {
    const activeId = chat.getConvId();
    try {
      groups = await util.apiGroups({ q: searchTerm(), mine: onlyMine() ? 1 : 0 });
    } catch { groups = []; }

    const wasOpen = new Set([...sections.entries()].filter(([, s]) => s.open).map(([k]) => k));
    const active = findLoadedConv(activeId);
    const open = wasOpen.size ? wasOpen : defaultOpenKeys(active);
    if (searchTerm()) for (const g of groups) open.add(groupKey(g));
    if (active) open.add(active.company_id === null ? 'none' : String(active.company_id));

    const keys = new Set(groups.map(groupKey));
    for (const k of [...sections.keys()]) if (!keys.has(k)) sections.delete(k);
    for (const g of groups) {
      const key = groupKey(g);
      if (!sections.has(key)) sections.set(key, { convs: [], total: g.count, has_more: true, open: false });
      sections.get(key).open = open.has(key);
    }
    await Promise.all(
      [...sections.entries()].filter(([, s]) => s.open).map(([k]) => loadSection(k))
    );
    renderList();
  }

  function findLoadedConv(id) {
    if (!id) return null;
    for (const s of sections.values()) {
      const hit = s.convs.find((c) => c.id === id);
      if (hit) return hit;
    }
    return null;
  }

  // ───────────── Render ─────────────

  function rowOpts() {
    return {
      activeId: chat.getConvId(),
      currentUser,
      showDn: false,           // header section ĐÃ là doanh nghiệp — chip lặp lại là thừa
      onPick: (id) => { if (id !== chat.getConvId()) chat.loadConversation(id); },
      onChangeCompany: openCompanyDialog,
      onDelete: async (id) => {
        if (!confirm('Xoá cuộc trò chuyện này?')) return;
        const dr = await util.apiDelete(id);
        if (!dr.ok) return;
        if (id === chat.getConvId()) newConversation();
        else refreshList();
      },
    };
  }

  function renderList() {
    const listEl = $('chat-list');
    listEl.innerHTML = '';
    if (!groups.length) {
      listEl.innerHTML = `<div class="ai-history-empty">${searchTerm()
        ? 'Không có cuộc nào khớp.'
        : 'Chưa có cuộc trò chuyện nào.<br>Hỏi gì đó để bắt đầu.'}</div>`;
      return;
    }
    const opts = rowOpts();
    for (const g of groups) {
      const key = groupKey(g);
      const state = sections.get(key);
      const section = util.el('section', { class: 'chat-group' + (state.open ? ' open' : '') });

      const head = util.el('button', {
        class: 'chat-group-head', type: 'button',
        'aria-expanded': state.open ? 'true' : 'false',
      });
      head.appendChild(util.el('span', { class: 'cg-caret', text: state.open ? '▾' : '▸' }));
      head.appendChild(util.el('span', { class: 'cg-name', text: g.company_name }));
      head.appendChild(util.el('span', { class: 'cg-count', text: String(g.count) }));
      head.addEventListener('click', async () => {
        state.open = !state.open;
        if (state.open && !state.convs.length) await loadSection(key);
        renderList();
      });
      section.appendChild(head);

      if (state.open) {
        const body = util.el('div', { class: 'chat-group-body' });
        for (const c of state.convs) body.appendChild(util.renderConversationRow(c, opts));
        if (state.has_more) {
          const more = util.el('button', {
            class: 'chat-group-more', type: 'button',
            text: `Tải thêm (còn ${state.total - state.convs.length})`,
          });
          more.addEventListener('click', async () => {
            await loadSection(key, { append: true });
            renderList();
          });
          body.appendChild(more);
        }
        section.appendChild(body);
      }
      listEl.appendChild(section);
    }
  }

  // ───────────── Đổi doanh nghiệp của một cuộc ─────────────

  async function openCompanyDialog(conv) {
    const dlg = $('chat-move-dialog');
    const select = $('chat-move-select');
    const err = $('chat-move-error');
    err.textContent = '';
    if (companyOptions === null) {
      try { companyOptions = await util.apiCompanies(); } catch { companyOptions = []; }
    }
    select.innerHTML = '';
    select.appendChild(util.el('option', { value: '', text: '— Chưa gán doanh nghiệp —' }));
    for (const c of companyOptions) {
      select.appendChild(util.el('option', { value: c.code, text: c.name }));
    }
    select.value = conv.company_id
      ? (companyOptions.find((c) => c.id === conv.company_id) || {}).code || ''
      : '';
    $('chat-move-title').textContent = conv.title || 'Cuộc trò chuyện';

    // Gắn lại handler MỖI lần mở. Lượt lưu hỏng (vd officer chọn DN ngoài quyền
    // → 404) mở lại hộp thoại, và nếu không gắn lại thì lần bấm Lưu sau đóng
    // hộp thoại mà không gọi API — thay đổi của cán bộ mất im lặng.
    const arm = () => {
      dlg.returnValue = '';
      dlg.addEventListener('close', onClose, { once: true });
      dlg.showModal();
    };
    async function onClose() {
      if (dlg.returnValue !== 'save') return;
      const r = await util.apiSetCompany(conv.id, select.value || null);
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        err.textContent = j.detail || `Không đổi được (HTTP ${r.status}).`;
        arm();
        return;
      }
      await refreshList();
    }
    arm();
  }

  function renderSuggestions() {
    const box = $('chat-suggestions');
    if (!box) return;
    box.innerHTML = '';
    for (const s of util.getSuggestions(util.getPageContext())) {
      const btn = util.el('button', { class: 'ai-suggestion', type: 'button', text: s });
      btn.addEventListener('click', () => chat.sendMessage(s));
      box.appendChild(btn);
    }
  }

  function showEmpty() {
    $('chat-messages').innerHTML = `
      <div class="ai-empty" style="margin:auto;max-width:540px">
        <p><strong>Trợ lý AI Audit-HQ</strong></p>
        <p style="font-size:13px;margin-top:6px">Hỏi về doanh nghiệp, phát hiện, pháp lý. Tôi tra cứu cơ sở dữ liệu ở chế độ chỉ đọc, truy vấn tổng hợp, xuất báo cáo và đề xuất chạy kiểm tra (cán bộ bấm xác nhận). Luôn đối chiếu nguồn — AI có thể sai.</p>
        <div id="chat-suggestions" class="ai-suggestions" style="margin-top:14px"></div>
      </div>`;
    renderSuggestions();
  }

  function newConversation() {
    chat.clearMessages();
    showEmpty();
    chat.setConvId(null);   // → onConvChange → pushState /chat + refresh list
    $('chat-input').focus();
  }

  // Đồng bộ URL + danh sách mỗi khi conv đổi (gửi xong, mở cuộc, tạo mới).
  function onConvChange(id) {
    const url = id ? '/chat/' + id : '/chat';
    if (window.location.pathname !== url) history.pushState({ convId: id }, '', url);
    refreshList();
  }

  async function init() {
    let meta;
    try { meta = await util.apiMeta(); } catch { meta = null; }
    if (!meta || !meta.enabled || !meta.configured) {
      $('chat-page-root').innerHTML =
        '<div class="ai-empty" style="padding:60px 20px;margin:auto">Trợ lý AI hiện đang tắt. ' +
        'Quản trị bật lại ở <a href="/admin/ai">Cấu hình AI</a>.</div>';
      return;
    }
    $('chat-model').textContent = meta.model || '';
    currentUser = meta.username || null;

    chat = window.AuditChat.create({
      messagesEl: $('chat-messages'),
      inputEl: $('chat-input'),
      submitEl: $('chat-submit'),
      isAdmin: meta.is_admin,
      onConversationChange: onConvChange,
    });

    // Form + phím tắt.
    const form = $('chat-form');
    const input = $('chat-input');
    form.addEventListener('submit', (e) => { e.preventDefault(); chat.sendMessage(input.value); });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
    });
    $('chat-new').addEventListener('click', newConversation);

    // Tìm kiếm chạy ở server (lọc xuyên mọi section, kể cả section chưa tải).
    let searchTimer = null;
    $('chat-search').addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { sections.clear(); refreshList(); }, 200);
    });

    isAdmin = !!meta.is_admin;
    const mineWrap = $('chat-mine-wrap');
    if (isAdmin && mineWrap) {
      mineWrap.hidden = false;
      const box = $('chat-mine');
      box.checked = onlyMine();
      box.addEventListener('change', () => {
        sessionStorage.setItem(MINE_KEY, box.checked ? '1' : '0');
        sections.clear();
        refreshList();
      });
    }

    window.addEventListener('popstate', () => {
      const id = pathConvId();
      if (id) chat.loadConversation(id);
      else { chat.clearMessages(); showEmpty(); chat.setConvId(null); }
    });

    // Tải danh sách + cuộc ban đầu (từ URL /chat/{id} hoặc rỗng).
    await refreshList();
    const initial = (typeof window.__CHAT_CONV_ID__ === 'number') ? window.__CHAT_CONV_ID__ : pathConvId();
    if (initial) await chat.loadConversation(initial);
    else showEmpty();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
