/* AI Assistant sidebar — mount FAB + panel trượt cho mọi trang.
 * Lõi chat (stream, render, tool pill, citation) nằm ở chat-core.js (AuditChat).
 * File này chỉ lo: panel toggle, overlay lịch sử, phạm vi doanh nghiệp, gợi ý, init.
 *
 * Phạm vi (ADR #20): panel quá ngắn để chia section như trang /chat, nên giữ
 * danh sách phẳng + chip doanh nghiệp mỗi dòng + bộ lọc, đọc CÙNG nhãn.
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'audit_hq_ai_conv_id';
  const FULL_KEY = 'audit_hq_ai_full';
  const SCOPE_KEY = 'audit_hq_ai_scope';   // mã DN cán bộ chọn cho cuộc mới (cùng tab)

  let metaCache = null;
  let chat = null;          // instance AuditChat
  let historyConvs = [];
  let companies = [];       // DN cán bộ được phép — đổ vào chip + bộ lọc
  let activeConv = null;    // {company_id, company_code, company_name} của cuộc đang mở

  const { util } = window.AuditChat;
  const $ = (id) => document.getElementById(id);

  // ───────────── Phạm vi doanh nghiệp ─────────────

  // Mã DN mà cuộc MỚI sẽ gắn: chip cán bộ chọn trong tab này thắng, sau đó tới
  // doanh nghiệp của trang đang xem.
  function scopeCode() {
    const chosen = sessionStorage.getItem(SCOPE_KEY);
    if (chosen !== null) return chosen || null;
    const ctx = util.getPageContext();
    return ctx.dn_code || null;
  }

  function companyByCode(code) {
    if (!code) return null;
    return companies.find((c) => c.code === code || c.slug === code) || null;
  }

  // Ngữ cảnh trang + phạm vi đã chọn — server nhận `scope_company_code` làm tín
  // hiệu ưu tiên cao nhất khi gắn nhãn cho cuộc mới.
  function pageContextWithScope() {
    const ctx = util.getPageContext();
    const code = scopeCode();
    if (code) ctx.scope_company_code = code;
    return ctx;
  }

  function renderScopeBar() {
    const bar = $('ai-scope-bar');
    const select = $('ai-scope');
    if (!bar || !select) return;
    if (!companies.length) { bar.hidden = true; return; }
    bar.hidden = false;
    const current = scopeCode();
    select.innerHTML = '';
    select.appendChild(util.el('option', { value: '', text: '— Không gắn doanh nghiệp —' }));
    for (const c of companies) {
      select.appendChild(util.el('option', { value: c.code, text: c.name }));
    }
    const match = companyByCode(current);
    select.value = match ? match.code : '';
  }

  // Cuộc đang mở gắn DN A trong khi trang đang xem là DN B → báo, không tự tách
  // cuộc và không tự đổi nhãn.
  function renderMismatch() {
    const box = $('ai-scope-mismatch');
    if (!box) return;
    const pageCode = util.getPageContext().dn_code;
    const pageCompany = companyByCode(pageCode);
    if (!activeConv || !activeConv.company_id || !pageCompany
        || activeConv.company_id === pageCompany.id) {
      box.hidden = true;
      return;
    }
    $('ai-scope-mismatch-text').textContent =
      `Cuộc trò chuyện này gắn với ${activeConv.company_name} · bạn đang xem ${pageCompany.name}`;
    $('ai-scope-mismatch-new').textContent = `Mở cuộc trò chuyện mới cho ${pageCompany.name}`;
    box.hidden = false;
  }

  function setActiveConv(data) {
    activeConv = data
      ? {
        company_id: data.company_id ?? null,
        company_code: data.company_code ?? null,
        company_name: data.company_name || data.company_code || null,
      }
      : null;
    renderMismatch();
  }

  // ───────────── History overlay ─────────────
  async function openHistory() {
    $('ai-history-panel').hidden = false;
    const listBox = $('ai-history-list');
    listBox.innerHTML = '<div class="ai-history-empty">Đang tải...</div>';
    const search = $('ai-history-search');
    if (search) search.value = '';
    renderHistoryFilter();
    try {
      historyConvs = await util.apiList({ mine: 1, limit: 50 });
      renderHistory('');
    } catch (e) {
      listBox.innerHTML = `<div class="ai-history-empty">Lỗi tải lịch sử: ${e.message}</div>`;
    }
  }

  function renderHistoryFilter() {
    const select = $('ai-history-company');
    if (!select) return;
    const keep = select.value;
    select.innerHTML = '';
    select.appendChild(util.el('option', { value: '', text: 'Mọi doanh nghiệp' }));
    for (const c of companies) {
      select.appendChild(util.el('option', { value: String(c.id), text: c.name }));
    }
    select.appendChild(util.el('option', { value: 'none', text: 'Chưa gán doanh nghiệp' }));
    select.value = keep;
  }

  function renderHistory(filter) {
    const companyFilter = ($('ai-history-company') || {}).value || '';
    const convs = historyConvs.filter((c) => {
      if (!companyFilter) return true;
      if (companyFilter === 'none') return c.company_id === null;
      return String(c.company_id) === companyFilter;
    });
    util.renderConversationList($('ai-history-list'), convs, {
      activeId: chat.getConvId(),
      currentUser: metaCache.username,
      filter,
      onPick: (id) => { closeHistory(); openConversation(id); },
      onDelete: async (id) => {
        if (!confirm('Xoá cuộc trò chuyện này?')) return;
        const dr = await util.apiDelete(id);
        if (dr.ok) {
          if (id === chat.getConvId()) { chat.setConvId(null); chat.clearMessages(); setActiveConv(null); }
          historyConvs = historyConvs.filter((x) => x.id !== id);
          const s = $('ai-history-search');
          renderHistory(s ? s.value : '');
        }
      },
    });
  }

  function closeHistory() { $('ai-history-panel').hidden = true; }

  async function openConversation(id) {
    const data = await chat.loadConversation(id);
    setActiveConv(data);
  }

  function startNewConversation() {
    chat.setConvId(null);
    setActiveConv(null);
    closeHistory();
    chat.clearMessages();
    const scoped = companyByCode(scopeCode());
    $('ai-messages').innerHTML = `
      <div class="ai-empty">
        <p><strong>Cuộc trò chuyện mới.</strong></p>
        ${scoped ? `<p class="ai-scope-note">Sẽ gắn với ${scoped.name}.</p>` : ''}
        <div id="ai-suggestions" class="ai-suggestions"></div>
      </div>`;
    renderSuggestions();
  }

  // ───────────── Suggestions ─────────────
  function renderSuggestions() {
    const box = $('ai-suggestions');
    if (!box) return;
    box.innerHTML = '';
    for (const s of util.getSuggestions(util.getPageContext())) {
      const btn = util.el('button', { class: 'ai-suggestion', type: 'button', text: s });
      btn.addEventListener('click', () => chat.sendMessage(s));
      box.appendChild(btn);
    }
  }

  // ───────────── Panel toggle ─────────────
  async function openPanel() {
    const panel = $('ai-panel');
    panel.classList.add('open');
    panel.setAttribute('aria-hidden', 'false');
    // `inert` đi cặp với `aria-hidden`, đặt ở CÙNG một chỗ: tách ra hai chỗ thì một chỗ
    // sửa mà chỗ kia không, và thanh đóng lại vẫn giữ sáu điều khiển trong chuỗi tab.
    panel.removeAttribute('inert');
    if (sessionStorage.getItem(FULL_KEY) === '1') panel.classList.add('full');
    updateExpandButton();
    await resumeOrStart();
    setTimeout(() => $('ai-input').focus(), 250);
  }
  function closePanel() {
    const panel = $('ai-panel');
    panel.classList.remove('open');
    panel.setAttribute('aria-hidden', 'true');
    panel.setAttribute('inert', '');
  }
  function toggleFull() {
    const isFull = $('ai-panel').classList.toggle('full');
    sessionStorage.setItem(FULL_KEY, isFull ? '1' : '0');
    updateExpandButton();
  }
  function updateExpandButton() {
    const btn = $('ai-expand');
    const isFull = $('ai-panel').classList.contains('full');
    btn.textContent = isFull ? '⊟' : '⛶';
    btn.setAttribute('title', isFull ? 'Thu nhỏ' : 'Phóng to');
  }

  // Mở panel: ghi nhớ trong cùng tab (sessionStorage) ưu tiên trước; nếu không
  // thì nối lại cuộc gần nhất CÙNG doanh nghiệp dưới 24 giờ (server quyết định
  // cửa sổ), quá hạn hoặc không có thì mở cuộc mới trong phạm vi đó.
  let resumeDone = false;
  async function resumeOrStart() {
    if (resumeDone) return;
    resumeDone = true;
    if (chat.getConvId()) return;
    const code = scopeCode();
    let data = null;
    try {
      const r = await fetch(
        '/api/chat/resume' + (code ? '?company_code=' + encodeURIComponent(code) : ''),
        { credentials: 'same-origin' },
      );
      if (r.ok) data = await r.json();
    } catch { data = null; }
    if (!data || !data.conversation_id) { startNewConversation(); return; }
    await openConversation(data.conversation_id);
    const label = data.company_name || data.company_code;
    $('ai-messages').insertBefore(
      util.el('div', {
        class: 'ai-resume-note',
        text: label
          ? `Đang tiếp tục cuộc trò chuyện gần nhất của ${label}.`
          : 'Đang tiếp tục cuộc trò chuyện gần nhất.',
      }),
      $('ai-messages').firstChild,
    );
  }

  // ───────────── Init ─────────────
  async function init() {
    try {
      metaCache = await util.apiMeta();
    } catch { return; }
    if (!metaCache.enabled || !metaCache.configured) return;

    const fab = $('ai-fab');
    if (!fab) return;
    fab.classList.remove('hidden');
    $('ai-model').textContent = metaCache.model || '';

    chat = window.AuditChat.create({
      messagesEl: $('ai-messages'),
      inputEl: $('ai-input'),
      submitEl: $('ai-submit'),
      isAdmin: metaCache.is_admin,
      pageContextFn: pageContextWithScope,
      onConversationChange: (id) => {
        if (id) sessionStorage.setItem(STORAGE_KEY, id);
        else sessionStorage.removeItem(STORAGE_KEY);
      },
    });

    try { companies = await util.apiCompanies(); } catch { companies = []; }
    renderScopeBar();
    renderHistoryFilter();

    fab.addEventListener('click', openPanel);
    $('ai-close').addEventListener('click', closePanel);
    $('ai-history').addEventListener('click', openHistory);
    $('ai-history-close').addEventListener('click', closeHistory);
    const histSearch = $('ai-history-search');
    if (histSearch) histSearch.addEventListener('input', () => renderHistory(histSearch.value));
    const histCompany = $('ai-history-company');
    if (histCompany) {
      histCompany.addEventListener('change', () => renderHistory(histSearch ? histSearch.value : ''));
    }
    $('ai-new').addEventListener('click', startNewConversation);
    $('ai-expand').addEventListener('click', toggleFull);

    // Đổi chip phạm vi chỉ ảnh hưởng cuộc tạo SAU đó — cuộc đang mở giữ nguyên.
    const scopeSelect = $('ai-scope');
    if (scopeSelect) {
      scopeSelect.addEventListener('change', () => {
        sessionStorage.setItem(SCOPE_KEY, scopeSelect.value);
        renderMismatch();
        if (!chat.getConvId()) startNewConversation();
      });
    }
    const mismatchBtn = $('ai-scope-mismatch-new');
    if (mismatchBtn) {
      mismatchBtn.addEventListener('click', () => {
        const pageCode = util.getPageContext().dn_code;
        const pageCompany = companyByCode(pageCode);
        sessionStorage.setItem(SCOPE_KEY, pageCompany ? pageCompany.code : '');
        renderScopeBar();
        startNewConversation();
      });
    }

    // Resume conv từ sessionStorage (cùng tab, sau refresh) — thắng quy tắc 24h.
    const savedConv = sessionStorage.getItem(STORAGE_KEY);
    if (savedConv) {
      const id = parseInt(savedConv, 10);
      const r = await util.apiMessages(id);
      if (r.ok) { await openConversation(id); resumeDone = true; }
      else sessionStorage.removeItem(STORAGE_KEY);
    }

    renderSuggestions();

    const form = $('ai-form');
    const input = $('ai-input');
    form.addEventListener('submit', (e) => { e.preventDefault(); chat.sendMessage(input.value); });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && $('ai-panel').classList.contains('open')) closePanel();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
