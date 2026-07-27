/* AI chat core — engine dùng chung cho sidebar (FAB) lẫn trang /chat.
 * Stream qua SSE /api/chat/stream, render markdown + citation, tool-use pill.
 * Mỗi "mount" gọi AuditChat.create({...}) để lấy 1 instance độc lập (state đóng
 * trong closure) rồi tự lo phần chrome riêng (panel / layout trang / danh sách).
 */
(function () {
  'use strict';

  // ═══════════════ Utils (không phụ thuộc mount) ═══════════════
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

  // Nhãn loại trang (tiếng Việt) để AI biết user đang ở đâu, không chỉ DN/năm.
  function pageLabel(path) {
    if (path === '/companies') return 'Danh sách doanh nghiệp';
    if (/^\/companies\/[^/]+\/documents/.test(path)) return 'Quản lý tài liệu';
    if (/^\/companies\/[^/]+\/data/.test(path)) return 'Bảng dữ liệu Tầng 1';
    if (/^\/companies\/[^/]+\/items\//.test(path)) return 'Chi tiết mã hàng';
    if (/^\/companies\/[^/]+\/(upload|edit)/.test(path)) return 'Tải / sửa dữ liệu DN';
    if (/^\/companies\/[^/]+$/.test(path)) return 'Tổng quan doanh nghiệp';
    if (/^\/findings\/\d+/.test(path)) return 'Chi tiết phát hiện';
    if (path.startsWith('/chat')) return 'Trợ lý AI (trang riêng)';
    if (path.startsWith('/admin/checks/new')) return 'Soạn kiểm tra mở rộng';
    if (path.startsWith('/admin/')) return 'Trang quản trị';
    if (path.startsWith('/jobs')) return 'Hàng đợi công việc';
    if (path.startsWith('/danh-muc-kiem-tra')) return 'Danh mục kiểm tra';
    if (path.startsWith('/tai-lieu')) return 'Tài liệu hướng dẫn';
    return null;
  }

  function getPageContext() {
    const path = window.location.pathname;
    const search = window.location.search;
    const params = new URLSearchParams(search);
    const ctx = { url: path + search };
    let m;
    if ((m = path.match(/^\/companies\/([A-Za-z0-9_-]+)/))) {
      ctx.dn_code = m[1];
    }
    const yr = params.get('year');
    if (yr && /^\d{4}$/.test(yr)) ctx.year = parseInt(yr, 10);
    if ((m = path.match(/^\/findings\/(\d+)/))) {
      ctx.finding_id = parseInt(m[1], 10);
    }
    if ((m = path.match(/^\/companies\/[A-Za-z0-9_-]+\/items\/([^/?#]+)/))) {
      ctx.item_code = decodeURIComponent(m[1]);
    }
    if (/^\/companies\/[A-Za-z0-9_-]+\/data/.test(path)) {
      ctx.table = params.get('table') || 'm15';
      if (params.get('q')) ctx.q = params.get('q');
    }
    const label = pageLabel(path);
    if (label) ctx.view_label = label;
    return ctx;
  }

  function getSuggestions(ctx) {
    const out = [];
    if (ctx.finding_id) {
      out.push('Giải thích finding này — căn cứ pháp lý và mức độ nghiêm trọng?');
    } else if (ctx.item_code && ctx.dn_code) {
      out.push(`Phân tích mã hàng ${ctx.item_code} của ${ctx.dn_code} qua các năm.`);
      out.push(`Mã ${ctx.item_code} có phát hiện (finding) nào không?`);
    } else if (ctx.table && ctx.dn_code) {
      out.push(`Bảng ${ctx.table.toUpperCase()} của ${ctx.dn_code}${ctx.year ? ' năm ' + ctx.year : ''} có bất thường gì?`);
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
  const TABLE_ALIASES = {
    nvl_balances: 'm15', sp_balances: 'm15a', norms: 'm16', bcct: 'bcct',
    m15: 'm15', m15a: 'm15a', m16: 'm16',
    declaration_lines: 'declaration_lines',
  };

  function parseCitations(html) {
    return html.replace(/\[([a-z_]+):([^\]]+)\]/gi, (full, kind, val) => {
      const safeVal = val.replace(/"/g, '&quot;');
      if (kind === 'finding') {
        const single = val.trim();
        if (/^\d+$/.test(single)) {
          return `<a href="/findings/${single}" class="cite" title="Mở finding">📎 finding ${single}</a>`;
        }
        return `<span class="cite" title="Nhiều phát hiện">📎 finding ${safeVal}</span>`;
      }
      if (kind === 'check') {
        return `<span class="cite" title="Mã kiểm tra">${kind}:${safeVal}</span>`;
      }
      if (kind === 'item') {
        const ctx = getPageContext();
        if (ctx.dn_code) {
          const yearPart = ctx.year ? `?year=${ctx.year}` : '';
          const href = `/companies/${encodeURIComponent(ctx.dn_code)}/items/${encodeURIComponent(val)}${yearPart}`;
          return `<a href="${href}" class="cite" title="Trang chi tiết mã ${safeVal}">🔎 ${safeVal}</a>`;
        }
        return `<span class="cite" title="Mã hàng">🔎 ${safeVal}</span>`;
      }
      const tbl = TABLE_ALIASES[kind.toLowerCase()];
      if (tbl) {
        const ctx = getPageContext();
        const m = val.match(/(?:row_no|row_id|item_code|material_code)=([^,\s]+)/i);
        const qVal = m ? m[1] : val;
        if (ctx.dn_code && ctx.year && tbl !== 'declaration_lines') {
          const href = `/companies/${encodeURIComponent(ctx.dn_code)}/data?year=${ctx.year}&table=${tbl}&q=${encodeURIComponent(qVal)}`;
          return `<a href="${href}" class="cite" title="Xem dữ liệu nguồn (${kind})">📊 ${kind}:${safeVal}</a>`;
        }
        return `<span class="cite" title="Nguồn dữ liệu: ${kind}">📊 ${kind}:${safeVal}</span>`;
      }
      return `<span class="cite" title="Nguồn dữ liệu">${kind}:${safeVal}</span>`;
    });
  }

  function renderMarkdown(text) {
    if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
      return escapeHtml(text).replace(/\n/g, '<br>');
    }
    const html = marked.parse(text, { breaks: true, gfm: true });
    const clean = DOMPurify.sanitize(html, { ADD_ATTR: ['target'] });
    return parseCitations(clean);
  }

  function dateBucket(iso) {
    if (!iso) return 'Cũ hơn';
    const d = new Date(iso);
    const now = new Date();
    const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const dDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diffDays = Math.round((startToday - dDay) / 86400000);
    if (diffDays <= 0) return 'Hôm nay';
    if (diffDays === 1) return 'Hôm qua';
    if (diffDays <= 7) return '7 ngày qua';
    return 'Cũ hơn';
  }

  // Nhãn DN của cuộc — đọc từ dòng cuộc (server gắn lúc tạo, ADR #20). Cuộc mở
  // từ trang phát hiện có nhãn đúng; không còn suy từ page_url_seed.
  function convDnCode(c) {
    return c.company_code || null;
  }
  function convDnLabel(c) {
    return c.company_name || c.company_code || null;
  }

  // ═══════════════ API helpers ═══════════════
  async function apiMeta() {
    const r = await fetch('/api/ai/meta', { credentials: 'same-origin' });
    if (!r.ok) throw new Error('meta ' + r.status);
    return r.json();
  }
  async function apiList() {
    const r = await fetch('/api/chat/conversations', { credentials: 'same-origin' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return (await r.json()).conversations || [];
  }
  function apiMessages(id) {
    return fetch(`/api/chat/conversations/${id}/messages`, { credentials: 'same-origin' });
  }
  function apiDelete(id) {
    return fetch(`/api/chat/conversations/${id}`, { method: 'DELETE', credentials: 'same-origin' });
  }

  // ═══════════════ Danh sách cuộc trò chuyện (dùng chung) ═══════════════
  // listEl: container; convs: mảng từ apiList(); opts: {activeId, filter, onPick, onDelete}
  function renderConversationList(listEl, convs, opts = {}) {
    const f = (opts.filter || '').trim().toLowerCase();
    const items = convs.filter((c) => {
      if (!f) return true;
      const dn = ((c.company_code || '') + ' ' + (c.company_name || '')).toLowerCase();
      return (c.title || '').toLowerCase().includes(f) || dn.includes(f);
    });
    if (items.length === 0) {
      listEl.innerHTML = `<div class="ai-history-empty">${f
        ? 'Không có cuộc nào khớp.'
        : 'Chưa có cuộc trò chuyện nào.<br>Hỏi gì đó để bắt đầu.'}</div>`;
      return;
    }
    listEl.innerHTML = '';
    let lastBucket = null;
    for (const c of items) {
      const bucket = dateBucket(c.started_at);
      if (bucket !== lastBucket) {
        listEl.appendChild(el('div', { class: 'ai-history-group', text: bucket }));
        lastBucket = bucket;
      }
      const item = el('div', {
        class: 'ai-history-item' + (c.id === opts.activeId ? ' active' : ''),
        'data-conv-id': String(c.id),
      });
      const title = el('div', { class: 'h-title', text: c.title });
      const meta = el('div', { class: 'h-meta' });
      const dn = convDnLabel(c);
      if (dn) meta.appendChild(el('span', { class: 'h-dn', text: dn, title: c.company_code || dn }));
      // Cuộc của user khác (admin đang giám sát) → hiện chủ, không cho xoá.
      const isOther = c.owner && opts.currentUser && c.owner !== opts.currentUser;
      if (isOther) meta.appendChild(el('span', { class: 'h-owner', text: '👤 ' + c.owner }));
      const date = c.started_at ? new Date(c.started_at).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' }) : '';
      meta.appendChild(document.createTextNode(`${c.msg_count} tin nhắn · ${date}`));
      item.appendChild(title);
      item.appendChild(meta);
      if (!isOther) {
        const del = el('button', { class: 'h-delete', type: 'button', 'aria-label': 'Xoá', title: 'Xoá', text: '🗑' });
        del.addEventListener('click', (e) => { e.stopPropagation(); if (opts.onDelete) opts.onDelete(c.id); });
        item.appendChild(del);
      }
      item.addEventListener('click', () => { if (opts.onPick) opts.onPick(c.id); });
      listEl.appendChild(item);
    }
  }

  // ═══════════════ Chat instance ═══════════════
  // cfg: { messagesEl, inputEl, submitEl, isAdmin, pageContextFn?, onConversationChange? }
  function create(cfg) {
    const messagesEl = cfg.messagesEl;
    const inputEl = cfg.inputEl;
    const submitEl = cfg.submitEl;
    const isAdmin = !!cfg.isAdmin;
    const pageCtxFn = cfg.pageContextFn || getPageContext;
    const onConvChange = cfg.onConversationChange || function () {};

    let convId = null;
    let isStreaming = false;
    let currentToolStrip = null;   // {root, pills, detail} của lượt hiện tại
    let pendingToolPill = null;    // pill 'running' đang chờ tool_result khớp
    let pendingMentions = [];      // mention @DN/@finding user đã chọn (gửi kèm message)

    function scrollToBottom() { messagesEl.scrollTop = messagesEl.scrollHeight; }
    function clearEmpty() { const e = messagesEl.querySelector('.ai-empty'); if (e) e.remove(); }

    function addMessage(role, content, opts = {}) {
      const node = el('div', { class: `ai-msg ${role}${opts.streaming ? ' streaming' : ''}` });
      if (opts.html) node.innerHTML = content;
      else node.textContent = content;
      messagesEl.appendChild(node);
      scrollToBottom();
      return node;
    }

    // ── Tool-use compact pills ──
    function resetToolStrip() { currentToolStrip = null; pendingToolPill = null; }

    function ensureToolStrip() {
      if (currentToolStrip) return currentToolStrip;
      const root = el('div', { class: 'ai-tool-strip' });
      const pills = el('div', { class: 'ai-tool-pills' });
      const detail = el('pre', { class: 'ai-tool-detail' });
      detail.hidden = true;
      root.appendChild(pills);
      root.appendChild(detail);
      messagesEl.appendChild(root);
      currentToolStrip = { root, pills, detail };
      return currentToolStrip;
    }

    function wireToolDetail(pill, preview) {
      const text = preview || '(không có preview)';
      pill.title = 'Bấm để xem / ẩn chi tiết';
      pill.addEventListener('click', () => {
        const strip = pill.closest('.ai-tool-strip');
        if (!strip) return;
        const detail = strip.querySelector('.ai-tool-detail');
        const wasActive = pill.classList.contains('active');
        strip.querySelectorAll('.ai-tool-pill').forEach((p) => p.classList.remove('active'));
        if (wasActive) {
          detail.hidden = true;
        } else {
          pill.classList.add('active');
          detail.textContent = text;
          detail.hidden = false;
        }
        scrollToBottom();
      });
    }

    function addToolPillRunning(name) {
      const strip = ensureToolStrip();
      const pill = el('button', { class: 'ai-tool-pill running', type: 'button' });
      pill.appendChild(el('span', { class: 'tp-icon', text: '⚙' }));
      pill.appendChild(el('span', { class: 'tp-name', text: name || 'tool' }));
      pill.appendChild(el('span', { class: 'tp-dots', text: '…' }));
      strip.pills.appendChild(pill);
      pendingToolPill = pill;
      scrollToBottom();
      return pill;
    }

    function setPillDone(pill, name, preview) {
      pill.className = 'ai-tool-pill done';
      pill.textContent = '';
      pill.appendChild(el('span', { class: 'tp-icon', text: '✓' }));
      pill.appendChild(el('span', { class: 'tp-name', text: name || 'tool' }));
      wireToolDetail(pill, preview);
    }

    function addDoneToolPill(name, preview) {
      const strip = ensureToolStrip();
      const pill = el('button', { class: 'ai-tool-pill done', type: 'button' });
      pill.appendChild(el('span', { class: 'tp-icon', text: '✓' }));
      pill.appendChild(el('span', { class: 'tp-name', text: name || 'tool' }));
      wireToolDetail(pill, preview);
      strip.pills.appendChild(pill);
      scrollToBottom();
      return pill;
    }

    // tool_result khớp pill 'running' gần nhất — backend phát call→result tuần tự từng tool.
    function completeToolPill(name, preview) {
      const pill = pendingToolPill;
      pendingToolPill = null;
      if (pill) { setPillDone(pill, name, preview); scrollToBottom(); return pill; }
      return addDoneToolPill(name, preview);  // không có pill chờ (vd resume) → tạo thẳng done
    }

    // ── Chip tải file + thẻ xác nhận hành động ──
    function renderDownloadChip(data) {
      clearEmpty();
      const wrap = el('div', { class: 'ai-msg assistant' });
      const a = el('a', { class: 'ai-dl-chip', href: data.download_url, target: '_blank', rel: 'noopener' });
      if (data.title) {
        a.textContent = `⬇️ Tải Excel: ${data.title.length > 50 ? data.title.slice(0, 50) + '…' : data.title}`;
      } else {
        a.textContent = `⬇️ Tải báo cáo Excel${data.year ? ' năm ' + data.year : ''}`;
      }
      wrap.appendChild(a);
      messagesEl.appendChild(wrap);
      scrollToBottom();
    }

    function renderActionProposal(data) {
      clearEmpty();
      const card = el('div', { class: 'ai-action-confirm' });
      card.appendChild(el('div', { class: 'aac-label', text: '▶ ' + (data.label || 'Chạy kiểm tra') }));
      if (data.note) card.appendChild(el('div', { class: 'aac-note', text: data.note }));
      const actions = el('div', { class: 'aac-actions' });
      const btn = el('button', { class: 'aac-run', type: 'button', text: 'Xác nhận chạy' });
      const status = el('span', { class: 'aac-status' });
      btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.textContent = 'Đang tạo...';
        try {
          const r = await fetch('/api/chat/run-checks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ company_code: data.company_code, year: data.year ?? null }),
            credentials: 'same-origin',
          });
          const j = await r.json();
          if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
          btn.remove();
          status.innerHTML = `✓ Đã tạo công việc #${j.job_id} — <a href="${j.status_url}" target="_blank" rel="noopener">xem tiến độ</a>`;
        } catch (e) {
          btn.disabled = false;
          btn.textContent = 'Xác nhận chạy';
          status.textContent = `❌ ${e.message}`;
        }
      });
      actions.appendChild(btn);
      actions.appendChild(status);
      card.appendChild(actions);
      messagesEl.appendChild(card);
      scrollToBottom();
    }

    function handleEvent(event, data, assistantNode, appendText) {
      switch (event) {
        case 'content':
          appendText(data.text || '');
          break;
        case 'tool_call':
          if (isAdmin) addToolPillRunning(data.name);
          break;
        case 'tool_result':
          if (data.download_url) renderDownloadChip(data);  // chip hiện cho mọi cán bộ
          if (isAdmin) completeToolPill(data.name, data.preview || '(no preview)');
          break;
        case 'action_proposal':
          renderActionProposal(data);
          break;
        case 'done':
          setConvId(data.conversation_id);
          if (assistantNode && assistantNode.textContent.trim()) {
            messagesEl.appendChild(el('div', { class: 'ai-msg-foot', text: '⚠️ AI có thể sai — hãy kiểm chứng số liệu với nguồn.' }));
          }
          if (data.usage) {
            const u = data.usage;
            const stats = el('div', { class: 'ai-meta', style: 'font-size:10px;color:#9ca3af;align-self:flex-start;margin-top:-8px' });
            stats.textContent = `${u.model} · ${u.tokens_in}+${u.tokens_out} tokens`;
            messagesEl.appendChild(stats);
          }
          break;
        case 'error':
          if (assistantNode) assistantNode.classList.remove('streaming');
          addMessage('error', `❌ ${data.detail || 'Unknown error'}`);
          break;
      }
    }

    async function sendMessage(text, _retry = false) {
      if (isStreaming || !text.trim()) return;
      isStreaming = true;
      clearEmpty();
      if (!_retry) addMessage('user', text);
      submitEl.disabled = true;
      inputEl.disabled = true;
      resetToolStrip();
      const assistantNode = addMessage('assistant', '', { streaming: true, html: true });
      let accText = '';

      try {
        const resp = await fetch('/api/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
          body: JSON.stringify({
            message: text,
            conversation_id: _retry ? null : convId,
            page_context: pageCtxFn(),
            mentions: collectMentions(text),
          }),
          credentials: 'same-origin',
        });

        // 404 = conv_id stale (server đã xoá). Reset rồi retry 1 lần với conv mới.
        if (resp.status === 404 && convId && !_retry) {
          setConvId(null);
          assistantNode.remove();
          isStreaming = false; submitEl.disabled = false; inputEl.disabled = false;
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
          let idx;
          while ((idx = buf.indexOf('\n\n')) >= 0) {
            const block = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            if (!block.trim()) continue;
            let event = 'message';
            let data = '';
            for (const line of block.split('\n')) {
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
        if (pendingToolPill) {
          pendingToolPill.classList.remove('running');
          const dots = pendingToolPill.querySelector('.tp-dots');
          if (dots) dots.remove();
          pendingToolPill = null;
        }
        addMessage('error', `❌ ${e.message}`);
      } finally {
        assistantNode.classList.remove('streaming');
        isStreaming = false;
        submitEl.disabled = false;
        inputEl.disabled = false;
        inputEl.value = '';
        inputEl.focus();
        pendingMentions = [];
      }
    }

    // Mention còn nằm trong text → đính kèm (dedupe). Xoá khỏi text = bỏ mention.
    function collectMentions(text) {
      const seen = new Set();
      const out = [];
      for (const m of pendingMentions) {
        if (!text.includes(m.token)) continue;
        const key = m.type + ':' + (m.id != null ? m.id : m.code);
        if (seen.has(key)) continue;
        seen.add(key);
        out.push(m.type === 'finding' ? { type: 'finding', id: m.id } : { type: 'company', code: m.code });
      }
      return out;
    }

    function clearMessages() {
      messagesEl.innerHTML = '';
      resetToolStrip();
    }

    async function loadConversation(id) {
      try {
        const r = await apiMessages(id);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        setConvId(data.conversation_id);
        clearMessages();
        for (const m of data.messages) {
          if (m.role === 'user') {
            resetToolStrip();
            addMessage('user', m.content);
          } else if (m.role === 'assistant' && m.content) {
            resetToolStrip();
            addMessage('assistant', renderMarkdown(m.content), { html: true });
          } else if (m.role === 'tool' && isAdmin) {
            const preview = m.content.length > 300 ? m.content.slice(0, 300) + '…' : m.content;
            addDoneToolPill(m.tool_name || 'tool', preview);
          }
        }
        return data;
      } catch (e) {
        addMessage('error', `❌ Không tải được cuộc trò chuyện: ${e.message}`);
        return null;
      }
    }

    function setConvId(id) { convId = id; onConvChange(id); }

    // ── Mention @DN/@finding: autocomplete trên inputEl ──
    function attachMentions() {
      const pop = el('div', { class: 'ai-mention-pop' });
      pop.hidden = true;
      document.body.appendChild(pop);
      let items = [];
      let active = -1;
      let tStart = -1;   // vị trí ký tự '@' trong value
      let seq = 0;

      function close() { pop.hidden = true; items = []; active = -1; tStart = -1; }

      function position() {
        const r = inputEl.getBoundingClientRect();
        pop.style.left = r.left + 'px';
        pop.style.width = Math.max(220, r.width) + 'px';
        pop.style.bottom = (window.innerHeight - r.top + 6) + 'px';  // nổi PHÍA TRÊN ô nhập
      }

      function render() {
        if (!items.length) { close(); return; }
        pop.innerHTML = '';
        items.forEach((it, i) => {
          const row = el('div', { class: 'ai-mention-item' + (i === active ? ' active' : '') });
          row.appendChild(el('span', { class: 'mi-icon', text: it.type === 'finding' ? '📎' : '🏢' }));
          row.appendChild(el('span', { class: 'mi-label', text: it.label }));
          const sub = it.type === 'company' ? it.code : (it.company_code || '');
          if (sub) row.appendChild(el('span', { class: 'mi-sub', text: sub }));
          row.addEventListener('mousedown', (e) => { e.preventDefault(); choose(i); });
          pop.appendChild(row);
        });
        position();
        pop.hidden = false;
      }

      function choose(i) {
        const it = items[i];
        if (!it) return;
        const insert = it.type === 'finding' ? ('@#' + it.id) : ('@' + it.label);
        const before = inputEl.value.slice(0, tStart);
        const after = inputEl.value.slice(inputEl.selectionStart);
        inputEl.value = before + insert + ' ' + after;
        const caret = (before + insert + ' ').length;
        inputEl.setSelectionRange(caret, caret);
        pendingMentions.push({ token: insert, type: it.type, code: it.code, id: it.id });
        close();
        inputEl.focus();
      }

      async function query() {
        const val = inputEl.value.slice(0, inputEl.selectionStart);
        const m = val.match(/@([^\s@]*)$/);
        if (!m) { close(); return; }
        tStart = inputEl.selectionStart - m[0].length;
        const mine = ++seq;
        try {
          const r = await fetch('/api/chat/mentions?q=' + encodeURIComponent(m[1]), { credentials: 'same-origin' });
          if (mine !== seq) return;  // bỏ kết quả cũ (race)
          const data = await r.json();
          items = data.items || [];
          active = items.length ? 0 : -1;
          render();
        } catch { close(); }
      }

      inputEl.addEventListener('input', query);
      // Đăng ký TRƯỚC handler submit của mount → stopImmediatePropagation chặn submit khi popup mở.
      inputEl.addEventListener('keydown', (e) => {
        if (pop.hidden || !items.length) return;
        if (e.key === 'ArrowDown') { e.preventDefault(); e.stopImmediatePropagation(); active = (active + 1) % items.length; render(); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); e.stopImmediatePropagation(); active = (active - 1 + items.length) % items.length; render(); }
        else if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); e.stopImmediatePropagation(); choose(active); }
        else if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); close(); }
      });
      inputEl.addEventListener('blur', () => setTimeout(close, 150));
    }

    if (inputEl) attachMentions();

    return {
      sendMessage,
      loadConversation,
      clearMessages,
      getConvId: () => convId,
      setConvId,
      isStreaming: () => isStreaming,
    };
  }

  window.AuditChat = {
    create,
    util: {
      el, escapeHtml, getPageContext, getSuggestions, renderMarkdown, parseCitations,
      dateBucket, convDnCode, convDnLabel, apiMeta, apiList, apiMessages, apiDelete,
      renderConversationList,
    },
  };
})();
