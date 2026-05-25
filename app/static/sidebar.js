/* AI Assistant sidebar — vanilla JS, no framework.
 * Streams responses qua SSE /api/chat/stream. Citation post-process render link.
 */

(function () {
  'use strict';

  const STORAGE_KEY = 'audit_hq_ai_conv_id';

  let convId = null;
  let isStreaming = false;
  let metaCache = null;

  // ───────────── Page context auto-detect ─────────────
  function getPageContext() {
    const path = window.location.pathname;
    const search = window.location.search;
    const ctx = { url: path + search };
    let m;
    if ((m = path.match(/^\/companies\/([A-Za-z0-9_-]+)/))) {
      ctx.dn_code = m[1];
    }
    if ((m = search.match(/[?&]year=(\d{4})/))) {
      ctx.year = parseInt(m[1], 10);
    }
    if ((m = path.match(/^\/findings\/(\d+)/))) {
      ctx.finding_id = parseInt(m[1], 10);
    }
    return ctx;
  }

  function getSuggestions(ctx) {
    const out = [];
    if (ctx.finding_id) {
      out.push('Giải thích finding này — căn cứ pháp lý và mức độ nghiêm trọng?');
    } else if (ctx.dn_code && ctx.year) {
      out.push(`Tóm tắt rủi ro DN ${ctx.dn_code} năm ${ctx.year} trong 3 câu.`);
      out.push(`Liệt kê findings nghiêm trọng của ${ctx.dn_code} năm ${ctx.year}.`);
    } else if (ctx.dn_code) {
      out.push(`Tóm tắt DN ${ctx.dn_code} qua các năm.`);
    } else {
      out.push('Top 3 DN rủi ro cao nhất hiện nay?');
      out.push('Hệ thống chấm điểm rủi ro như thế nào?');
      out.push('Pháp lý nào hỗ trợ việc kiểm tra này?');
    }
    return out;
  }

  // ───────────── Citation parser ─────────────
  // [finding:123] → link tới /findings/123
  // [nvl_balances:row_no=88] / [m15:row_no=88] / [declaration_lines:item_code=ABC] → link viewer
  // [check:C2.3] → link tới /companies (no per-check page yet)
  function parseCitations(html) {
    return html.replace(/\[([a-z_]+):([^\]]+)\]/gi, (full, kind, val) => {
      const safeVal = val.replace(/"/g, '&quot;');
      if (kind === 'finding') {
        return `<a href="/findings/${encodeURIComponent(val)}" class="cite" title="Mở finding">📎 finding ${val}</a>`;
      }
      if (kind === 'check') {
        return `<span class="cite" title="Mã kiểm tra">${kind}:${safeVal}</span>`;
      }
      // table:filter — chỉ hiện badge (chưa có page truy thẳng row)
      return `<span class="cite" title="Nguồn dữ liệu">${kind}:${safeVal}</span>`;
    });
  }

  // ───────────── DOM helpers ─────────────
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else node.setAttribute(k, v);
    }
    for (const c of children) if (c) node.appendChild(c);
    return node;
  }

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderMarkdown(text) {
    if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
      // Fallback: plain text với line breaks
      return escapeHtml(text).replace(/\n/g, '<br>');
    }
    const html = marked.parse(text, { breaks: true, gfm: true });
    const clean = DOMPurify.sanitize(html, { ADD_ATTR: ['target'] });
    return parseCitations(clean);
  }

  function scrollToBottom() {
    const box = document.getElementById('ai-messages');
    box.scrollTop = box.scrollHeight;
  }

  function clearEmpty() {
    const empty = document.querySelector('#ai-messages .ai-empty');
    if (empty) empty.remove();
  }

  function addMessage(role, content, opts = {}) {
    const node = el('div', { class: `ai-msg ${role}${opts.streaming ? ' streaming' : ''}` });
    if (opts.html) {
      node.innerHTML = content;
    } else if (role === 'tool') {
      const nameSpan = el('span', { class: 'tool-name', text: opts.toolName || 'tool' });
      const sep = document.createTextNode(' · ');
      const preview = document.createTextNode(content.length > 200 ? content.slice(0, 200) + '…' : content);
      node.appendChild(nameSpan);
      node.appendChild(sep);
      node.appendChild(preview);
    } else {
      node.textContent = content;
    }
    document.getElementById('ai-messages').appendChild(node);
    scrollToBottom();
    return node;
  }

  // ───────────── Streaming send ─────────────
  async function sendMessage(text, _retryWithoutConv = false) {
    if (isStreaming || !text.trim()) return;
    isStreaming = true;
    clearEmpty();
    // Trên retry, đã add user message rồi — đừng add lần 2.
    if (!_retryWithoutConv) addMessage('user', text);

    const submitBtn = document.getElementById('ai-submit');
    const input = document.getElementById('ai-input');
    submitBtn.disabled = true;
    input.disabled = true;

    const assistantNode = addMessage('assistant', '', { streaming: true, html: true });
    let accText = '';

    try {
      const resp = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
        body: JSON.stringify({
          message: text,
          conversation_id: _retryWithoutConv ? null : convId,
          page_context: getPageContext(),
        }),
        credentials: 'same-origin',
      });

      // 404 = conv_id stale (server đã xoá). Reset rồi retry 1 lần với conv mới.
      if (resp.status === 404 && convId && !_retryWithoutConv) {
        convId = null;
        sessionStorage.removeItem(STORAGE_KEY);
        assistantNode.remove();
        isStreaming = false;
        submitBtn.disabled = false;
        input.disabled = false;
        return sendMessage(text, true);
      }

      if (!resp.ok) {
        const errText = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${errText.slice(0, 200)}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        // SSE parser: split on \n\n, each chunk has `event: X\ndata: Y`
        let idx;
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const block = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          if (!block.trim()) continue;
          const lines = block.split('\n');
          let event = 'message';
          let data = '';
          for (const line of lines) {
            if (line.startsWith('event:')) event = line.slice(6).trim();
            else if (line.startsWith('data:')) data += line.slice(5).trim();
          }
          let parsed;
          try { parsed = JSON.parse(data); } catch { parsed = data; }
          handleEvent(event, parsed, assistantNode, (delta) => {
            accText += delta;
            assistantNode.innerHTML = renderMarkdown(accText);
            scrollToBottom();
          });
        }
      }
    } catch (e) {
      assistantNode.classList.remove('streaming');
      addMessage('error', `❌ ${e.message}`);
    } finally {
      assistantNode.classList.remove('streaming');
      isStreaming = false;
      submitBtn.disabled = false;
      input.disabled = false;
      input.value = '';
      input.focus();
    }
  }

  function handleEvent(event, data, assistantNode, appendText) {
    switch (event) {
      case 'content':
        appendText(data.text || '');
        break;
      case 'tool_call':
        addMessage('tool', '⏳ đang gọi tool...', { toolName: data.name });
        break;
      case 'tool_result':
        // Append result preview vào tool message gần nhất
        addMessage('tool', data.preview || '(no preview)', { toolName: `${data.name} ✓` });
        break;
      case 'done':
        convId = data.conversation_id;
        sessionStorage.setItem(STORAGE_KEY, convId);
        // Optional: show usage stats footer
        if (data.usage) {
          const usage = data.usage;
          const stats = el('div', { class: 'ai-meta', style: 'font-size:10px;color:#9ca3af;align-self:flex-start;margin-top:-8px' });
          stats.textContent = `${usage.model} · ${usage.tokens_in}+${usage.tokens_out} tokens`;
          document.getElementById('ai-messages').appendChild(stats);
        }
        break;
      case 'error':
        assistantNode.classList.remove('streaming');
        addMessage('error', `❌ ${data.detail || 'Unknown error'}`);
        break;
    }
  }

  // ───────────── History panel ─────────────
  async function openHistory() {
    const panel = document.getElementById('ai-history-panel');
    panel.hidden = false;
    const listBox = document.getElementById('ai-history-list');
    listBox.innerHTML = '<div class="ai-history-empty">Đang tải...</div>';
    try {
      const r = await fetch('/api/chat/conversations', { credentials: 'same-origin' });
      const data = await r.json();
      const convs = data.conversations || [];
      if (convs.length === 0) {
        listBox.innerHTML = '<div class="ai-history-empty">Chưa có cuộc trò chuyện nào.<br>Hỏi gì đó để bắt đầu.</div>';
        return;
      }
      listBox.innerHTML = '';
      for (const c of convs) {
        const item = el('div', {
          class: 'ai-history-item' + (c.id === convId ? ' active' : ''),
          'data-conv-id': String(c.id),
        });
        const title = el('div', { class: 'h-title', text: c.title });
        const meta = el('div', { class: 'h-meta' });
        const date = c.started_at ? new Date(c.started_at).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' }) : '';
        meta.textContent = `${c.msg_count} tin nhắn · ${date}`;
        const del = el('button', { class: 'h-delete', type: 'button', 'aria-label': 'Xoá', title: 'Xoá', text: '🗑' });
        del.addEventListener('click', async (e) => {
          e.stopPropagation();
          if (!confirm('Xoá cuộc trò chuyện này?')) return;
          const dr = await fetch(`/api/chat/conversations/${c.id}`, { method: 'DELETE', credentials: 'same-origin' });
          if (dr.ok) {
            if (c.id === convId) {
              convId = null;
              sessionStorage.removeItem(STORAGE_KEY);
              clearChat();
            }
            openHistory();  // refresh list
          }
        });
        item.appendChild(title);
        item.appendChild(meta);
        item.appendChild(del);
        item.addEventListener('click', () => loadConversation(c.id));
        listBox.appendChild(item);
      }
    } catch (e) {
      listBox.innerHTML = `<div class="ai-history-empty">Lỗi tải lịch sử: ${e.message}</div>`;
    }
  }

  function closeHistory() {
    document.getElementById('ai-history-panel').hidden = true;
  }

  async function loadConversation(id) {
    closeHistory();
    try {
      const r = await fetch(`/api/chat/conversations/${id}/messages`, { credentials: 'same-origin' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      convId = data.conversation_id;
      sessionStorage.setItem(STORAGE_KEY, convId);
      clearChat();
      for (const m of data.messages) {
        if (m.role === 'user') {
          addMessage('user', m.content);
        } else if (m.role === 'assistant' && m.content) {
          addMessage('assistant', renderMarkdown(m.content), { html: true });
        } else if (m.role === 'tool') {
          const preview = m.content.length > 200 ? m.content.slice(0, 200) + '…' : m.content;
          addMessage('tool', preview, { toolName: `${m.tool_name || 'tool'} ✓` });
        }
      }
    } catch (e) {
      addMessage('error', `❌ Không tải được conversation: ${e.message}`);
    }
  }

  function clearChat() {
    document.getElementById('ai-messages').innerHTML = '';
  }

  function startNewConversation() {
    convId = null;
    sessionStorage.removeItem(STORAGE_KEY);
    closeHistory();
    clearChat();
    // Reset empty state + suggestions
    const box = document.getElementById('ai-messages');
    box.innerHTML = `
      <div class="ai-empty">
        <p><strong>Cuộc trò chuyện mới.</strong></p>
        <div id="ai-suggestions" class="ai-suggestions"></div>
      </div>`;
    renderSuggestions();
  }

  // ───────────── Suggestion buttons ─────────────
  function renderSuggestions() {
    const box = document.getElementById('ai-suggestions');
    if (!box) return;
    const ctx = getPageContext();
    box.innerHTML = '';
    for (const s of getSuggestions(ctx)) {
      const btn = el('button', { class: 'ai-suggestion', type: 'button', text: s });
      btn.addEventListener('click', () => sendMessage(s));
      box.appendChild(btn);
    }
  }

  // ───────────── Panel toggle ─────────────
  function openPanel() {
    document.getElementById('ai-panel').classList.add('open');
    document.getElementById('ai-panel').setAttribute('aria-hidden', 'false');
    setTimeout(() => document.getElementById('ai-input').focus(), 250);
  }
  function closePanel() {
    document.getElementById('ai-panel').classList.remove('open');
    document.getElementById('ai-panel').setAttribute('aria-hidden', 'true');
  }

  // ───────────── Init ─────────────
  async function init() {
    // Check meta first — hide FAB if AI disabled
    try {
      const r = await fetch('/api/ai/meta', { credentials: 'same-origin' });
      if (!r.ok) return;
      metaCache = await r.json();
    } catch { return; }
    if (!metaCache.enabled || !metaCache.configured) return;

    const fab = document.getElementById('ai-fab');
    if (!fab) return;
    fab.classList.remove('hidden');
    document.getElementById('ai-model').textContent = metaCache.model || '';

    fab.addEventListener('click', openPanel);
    document.getElementById('ai-close').addEventListener('click', closePanel);
    document.getElementById('ai-history').addEventListener('click', openHistory);
    document.getElementById('ai-history-close').addEventListener('click', closeHistory);
    document.getElementById('ai-new').addEventListener('click', startNewConversation);

    // Restore conv_id từ sessionStorage (resume sau page refresh trong cùng tab)
    const savedConv = sessionStorage.getItem(STORAGE_KEY);
    if (savedConv) {
      const id = parseInt(savedConv, 10);
      // Validate: nếu server đã xoá → clear silent. Nếu tồn tại → load transcript.
      try {
        const r = await fetch(`/api/chat/conversations/${id}/messages`, { credentials: 'same-origin' });
        if (r.ok) {
          await loadConversation(id);
        } else {
          sessionStorage.removeItem(STORAGE_KEY);
        }
      } catch {
        sessionStorage.removeItem(STORAGE_KEY);
      }
    }

    renderSuggestions();

    const form = document.getElementById('ai-form');
    const input = document.getElementById('ai-input');
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      sendMessage(input.value);
    });
    // Enter to submit, Shift+Enter for newline
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        form.requestSubmit();
      }
    });
    // ESC to close panel
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && document.getElementById('ai-panel').classList.contains('open')) {
        closePanel();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
