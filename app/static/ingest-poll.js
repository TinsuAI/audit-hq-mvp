/* Lượt nạp chạy nền — dòng kỳ tự cập nhật TẠI CHỖ (#89).
 *
 * Không có chữ tiếng Việt nào ở đây: tiêu đề, câu mô tả, ghi chú và nhãn nút đều
 * do điểm cuối trạng thái dựng sẵn (app/pipeline/ingest_status.py), nên lần render
 * đầu của server và lần cập nhật ở đây đọc cùng một nguồn chữ.
 *
 * Chỉ theo dõi khối mà SERVER đã đánh dấu đang chạy — trang này không tự tạo việc
 * nạp nào. Nhờ đó khối "đã nạp xong" render sẵn không bao giờ tự tải lại trang.
 *
 * Địa chỉ hỏi trạng thái nằm TRÊN CHÍNH KHỐI (`data-ingest-url`), dựng sẵn ở máy chủ
 * (#125): dòng kỳ và trang file cùng in khối này, và trang file phải hỏi kèm số hiệu
 * file để đích tải lại là chính nó. Ghép địa chỉ ở đây thì mỗi màn thêm một tham số
 * là một nhánh nữa trong JS.
 */
(function () {
  'use strict';

  const POLL_MS = 2000;
  const MAX_TRIES = 900;   // ~30 phút; job treo có đường lùi riêng ở điểm cuối

  function init() {
    const slots = document.querySelectorAll('.ds-ingest-slot[data-ingest-active="1"]');
    for (const slot of slots) {
      if (slot.dataset.ingestUrl) watch(slot, slot.dataset.ingestUrl);
    }
  }

  function watch(slot, url) {
    let tries = 0;
    const timer = setInterval(async () => {
      if (++tries > MAX_TRIES) { clearInterval(timer); return; }
      let data;
      try {
        const r = await fetch(url, { credentials: 'same-origin' });
        if (!r.ok) return;      // lỗi tạm thời → thử lại vòng sau
        data = await r.json();
      } catch { return; }

      if (data.status === null) { clearInterval(timer); slot.replaceChildren(); return; }
      render(slot, data);
      if (data.active) return;

      clearInterval(timer);
      slot.dataset.ingestActive = '0';
      if (data.reload_url) location.replace(data.reload_url);
    }, POLL_MS);
  }

  function render(slot, data) {
    slot.replaceChildren();
    if (!data.visible) return;

    const panel = document.createElement('div');
    panel.className = 'ds-ingest ds-ingest-' + data.tone;

    const title = document.createElement('p');
    title.className = 'ds-ingest-title';
    if (data.active) {
      const spin = document.createElement('span');
      spin.className = 'ds-ingest-spin';
      spin.setAttribute('aria-hidden', 'true');
      title.appendChild(spin);
    }
    title.appendChild(document.createTextNode(data.title));
    panel.appendChild(title);

    const detail = document.createElement('p');
    detail.className = 'ds-ingest-detail';
    detail.textContent = data.detail;
    panel.appendChild(detail);

    if (data.notes && data.notes.length) {
      const list = document.createElement('ul');
      list.className = 'ds-ingest-notes';
      for (const note of data.notes) {
        const li = document.createElement('li');
        li.textContent = note;
        list.appendChild(li);
      }
      panel.appendChild(list);
    }

    if (data.actions && data.actions.length) {
      const box = document.createElement('div');
      box.className = 'ds-ingest-actions';
      for (const action of data.actions) box.appendChild(actionNode(action));
      panel.appendChild(box);
    }

    slot.appendChild(panel);
  }

  function actionNode(action) {
    if (action.kind === 'post') {
      const form = document.createElement('form');
      form.method = 'post';
      form.action = action.url;
      const year = document.createElement('input');
      year.type = 'hidden';
      year.name = 'year';
      year.value = action.year == null ? '' : String(action.year);
      const button = document.createElement('button');
      button.type = 'submit';
      button.className = 'btn btn-sm btn-primary';
      button.textContent = action.label;
      form.append(year, button);
      return form;
    }
    const link = document.createElement('a');
    link.href = action.url;
    link.className = 'btn btn-sm btn-primary';
    link.textContent = action.label;
    return link;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
