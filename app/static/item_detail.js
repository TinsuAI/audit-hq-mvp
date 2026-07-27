// Item detail page: BCCT timeline + cross-year heatmap (ApexCharts).
// ApexCharts is loaded lazily — page degrades gracefully without JS.

(function () {
  function ensureApex(cb) {
    if (window.ApexCharts) { cb(); return; }
    var s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/apexcharts@3.49.1/dist/apexcharts.min.js';
    s.onload = cb;
    s.onerror = function () {
      console.warn('ApexCharts CDN failed; charts skipped.');
    };
    document.head.appendChild(s);
  }

  function fmt(n) {
    return new Intl.NumberFormat('vi-VN').format(n);
  }

  function renderTimeline() {
    var el = document.getElementById('bcct-timeline');
    if (!el) return;
    var raw;
    try { raw = JSON.parse(el.dataset.points || '[]'); } catch (e) { return; }
    if (!raw.length) return;
    var imports = raw.filter(function (p) { return p.op === 'import'; })
                     .map(function (p) { return { x: new Date(p.date).getTime(), y: p.qty, meta: p }; });
    var exports = raw.filter(function (p) { return p.op === 'export'; })
                     .map(function (p) { return { x: new Date(p.date).getTime(), y: p.qty, meta: p }; });
    var others  = raw.filter(function (p) { return p.op !== 'import' && p.op !== 'export'; })
                     .map(function (p) { return { x: new Date(p.date).getTime(), y: p.qty, meta: p }; });

    var series = [];
    if (imports.length) series.push({ name: 'Nhập', data: imports });
    if (exports.length) series.push({ name: 'Xuất', data: exports });
    if (others.length)  series.push({ name: 'Khác', data: others });

    new ApexCharts(el, {
      chart: { type: 'scatter', height: 220, zoom: { type: 'x', enabled: true }, toolbar: { show: false }, fontFamily: 'Inter, system-ui' },
      series: series,
      colors: ['#2563eb', '#dc2626', '#a3a3a3'],
      xaxis: { type: 'datetime', labels: { datetimeUTC: false } },
      yaxis: { title: { text: 'Lượng' }, labels: { formatter: fmt } },
      markers: { size: 6, hover: { size: 9 } },
      tooltip: {
        custom: function (opts) {
          var p = opts.w.config.series[opts.seriesIndex].data[opts.dataPointIndex].meta;
          return '<div class="apex-tip">'
            + '<div><strong>' + p.declaration_no + '</strong> · ' + p.customs_code + '</div>'
            + '<div>' + new Date(p.date).toLocaleDateString('vi-VN') + '</div>'
            + (p.partner ? '<div>' + p.partner + '</div>' : '')
            + '<div>Lượng: ' + fmt(p.qty) + '</div>'
            + '</div>';
        }
      },
      grid: { borderColor: '#eef2f7' },
    }).render();
  }

  function renderHeatmap() {
    var el = document.getElementById('item-heatmap');
    if (!el) return;
    var series;
    try { series = JSON.parse(el.dataset.series || '[]'); } catch (e) { return; }
    if (!series.length) return;

    new ApexCharts(el, {
      chart: { type: 'heatmap', height: 60 + series.length * 36, toolbar: { show: false }, fontFamily: 'Inter, system-ui' },
      series: series,
      dataLabels: { enabled: true, formatter: function (v) { return v > 0 ? fmt(v) : ''; }, style: { fontSize: '10px' } },
      colors: ['#2563eb'],
      plotOptions: {
        heatmap: {
          shadeIntensity: 0.6,
          radius: 4,
          colorScale: {
            ranges: [
              { from: -1, to: 0,        color: '#f3f4f6', name: '—' },
              { from: 1,  to: 1e18,     color: '#2563eb', name: 'có dữ liệu' },
            ]
          }
        }
      },
      xaxis: { type: 'category', title: { text: 'Năm' } },
      grid: { padding: { right: 16 } },
    }).render();
  }

  function wireAiPrompt() {
    document.querySelectorAll('[data-ai-prompt]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var prompt = btn.dataset.aiPrompt || '';
        // Open AI sidebar if exists, else fall back to copying to clipboard.
        if (window.AuditHQ && typeof window.AuditHQ.openAi === 'function') {
          window.AuditHQ.openAi(prompt);
          return;
        }
        var sidebar = document.querySelector('[data-ai-sidebar]');
        var input = document.querySelector('[data-ai-input]');
        if (input) {
          input.value = prompt;
          input.focus();
          if (sidebar && sidebar.classList) sidebar.classList.add('open');
          return;
        }
        navigator.clipboard && navigator.clipboard.writeText(prompt);
        btn.textContent = '📋 Đã chép câu hỏi';
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    wireAiPrompt();
    if (document.getElementById('bcct-timeline') || document.getElementById('item-heatmap')) {
      ensureApex(function () { renderTimeline(); renderHeatmap(); });
    }
  });
})();
