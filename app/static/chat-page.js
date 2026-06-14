/* Trang /chat — mount toàn trang dùng chung lõi AuditChat (chat-core.js).
 * Khác sidebar: danh sách cuộc luôn hiện bên trái + URL có nghĩa /chat/{id}
 * (history.pushState) + điều hướng back/forward.
 */
(function () {
  'use strict';

  const { util } = window.AuditChat;
  const $ = (id) => document.getElementById(id);

  let chat = null;
  let convs = [];
  let currentUser = null;

  function pathConvId() {
    const m = window.location.pathname.match(/^\/chat\/(\d+)/);
    return m ? parseInt(m[1], 10) : null;
  }

  function renderList() {
    util.renderConversationList($('chat-list'), convs, {
      activeId: chat.getConvId(),
      currentUser,
      filter: $('chat-search').value,
      onPick: (id) => { if (id !== chat.getConvId()) chat.loadConversation(id); },
      onDelete: async (id) => {
        if (!confirm('Xoá cuộc trò chuyện này?')) return;
        const dr = await util.apiDelete(id);
        if (!dr.ok) return;
        convs = convs.filter((x) => x.id !== id);
        if (id === chat.getConvId()) newConversation();
        else renderList();
      },
    });
  }

  async function refreshList() {
    try { convs = await util.apiList(); } catch { convs = []; }
    renderList();
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
    $('chat-search').addEventListener('input', renderList);
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
