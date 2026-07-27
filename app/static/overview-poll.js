/* Tổng quan AI sinh chạy nền — thay text TẠI CHỖ khi job xong (ADR #21 mục 6).
 *
 * Không reload trang: trang doanh nghiệp không khôi phục vị trí cuộn lẫn nhóm
 * đang mở, mà tổng quan là một đoạn nằm trong nhóm cán bộ đang đọc.
 */
(function () {
  'use strict';

  const POLL_MS = 3000;
  const MAX_TRIES = 200;   // ~10 phút rồi dừng; job treo được thu hồi riêng

  function init() {
    const pending = Array.from(document.querySelectorAll('.ov-pending'));
    if (!pending.length) return;

    const root = document.getElementById('company-detail-root');
    const base = root ? root.dataset.overviewUrl : null;
    const year = root ? root.dataset.year : null;
    if (!base || !year) return;

    for (const node of pending) watch(node, base, year, node.dataset.ovCheck);
  }

  function watch(node, base, year, check) {
    let tries = 0;
    const timer = setInterval(async () => {
      if (++tries > MAX_TRIES) { clearInterval(timer); return; }
      let data;
      try {
        const r = await fetch(
          `${base}?year=${encodeURIComponent(year)}&check=${encodeURIComponent(check)}`,
          { credentials: 'same-origin' },
        );
        if (!r.ok) return;      // lỗi tạm thời → thử lại vòng sau
        data = await r.json();
      } catch { return; }

      if (data.status === 'running' || data.status === null) return;
      clearInterval(timer);

      if (data.status === 'done') {
        const p = document.createElement('p');
        p.style.margin = '0';
        p.style.whiteSpace = 'pre-wrap';
        p.style.fontSize = 'var(--fs-sm)';
        p.textContent = data.content;
        node.replaceWith(p);
      } else {
        node.className = 'text-danger';
        node.textContent = '❌ Không viết được nhận định: ' + (data.error || 'lỗi không rõ');
        if (data.job_id) {
          const a = document.createElement('a');
          a.href = '/jobs/' + data.job_id;
          a.textContent = ' — xem công việc #' + data.job_id;
          node.appendChild(a);
        }
      }
    }, POLL_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
