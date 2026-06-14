/* AI Assistant sidebar — mount FAB + panel trượt cho mọi trang.
 * Lõi chat (stream, render, tool pill, citation) nằm ở chat-core.js (AuditChat).
 * File này chỉ lo: panel toggle, overlay lịch sử, gợi ý, init.
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'audit_hq_ai_conv_id';
  const FULL_KEY = 'audit_hq_ai_full';

  let metaCache = null;
  let chat = null;          // instance AuditChat
  let historyConvs = [];

  const { util } = window.AuditChat;
  const $ = (id) => document.getElementById(id);

  // ───────────── History overlay ─────────────
  async function openHistory() {
    $('ai-history-panel').hidden = false;
    const listBox = $('ai-history-list');
    listBox.innerHTML = '<div class="ai-history-empty">Đang tải...</div>';
    const search = $('ai-history-search');
    if (search) search.value = '';
    try {
      historyConvs = await util.apiList();
      renderHistory('');
    } catch (e) {
      listBox.innerHTML = `<div class="ai-history-empty">Lỗi tải lịch sử: ${e.message}</div>`;
    }
  }

  function renderHistory(filter) {
    util.renderConversationList($('ai-history-list'), historyConvs, {
      activeId: chat.getConvId(),
      currentUser: metaCache.username,
      filter,
      onPick: (id) => { closeHistory(); chat.loadConversation(id); },
      onDelete: async (id) => {
        if (!confirm('Xoá cuộc trò chuyện này?')) return;
        const dr = await util.apiDelete(id);
        if (dr.ok) {
          if (id === chat.getConvId()) { chat.setConvId(null); chat.clearMessages(); }
          historyConvs = historyConvs.filter((x) => x.id !== id);
          const s = $('ai-history-search');
          renderHistory(s ? s.value : '');
        }
      },
    });
  }

  function closeHistory() { $('ai-history-panel').hidden = true; }

  function startNewConversation() {
    chat.setConvId(null);
    closeHistory();
    chat.clearMessages();
    $('ai-messages').innerHTML = `
      <div class="ai-empty">
        <p><strong>Cuộc trò chuyện mới.</strong></p>
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
  function openPanel() {
    const panel = $('ai-panel');
    panel.classList.add('open');
    panel.setAttribute('aria-hidden', 'false');
    if (sessionStorage.getItem(FULL_KEY) === '1') panel.classList.add('full');
    updateExpandButton();
    setTimeout(() => $('ai-input').focus(), 250);
  }
  function closePanel() {
    $('ai-panel').classList.remove('open');
    $('ai-panel').setAttribute('aria-hidden', 'true');
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
      onConversationChange: (id) => {
        if (id) sessionStorage.setItem(STORAGE_KEY, id);
        else sessionStorage.removeItem(STORAGE_KEY);
      },
    });

    fab.addEventListener('click', openPanel);
    $('ai-close').addEventListener('click', closePanel);
    $('ai-history').addEventListener('click', openHistory);
    $('ai-history-close').addEventListener('click', closeHistory);
    const histSearch = $('ai-history-search');
    if (histSearch) histSearch.addEventListener('input', () => renderHistory(histSearch.value));
    $('ai-new').addEventListener('click', startNewConversation);
    $('ai-expand').addEventListener('click', toggleFull);

    // Resume conv từ sessionStorage (cùng tab, sau refresh).
    const savedConv = sessionStorage.getItem(STORAGE_KEY);
    if (savedConv) {
      const id = parseInt(savedConv, 10);
      const r = await util.apiMessages(id);
      if (r.ok) await chat.loadConversation(id);
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
