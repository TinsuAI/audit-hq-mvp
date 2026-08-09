/* Lưới ô cuộn ảo cho trang xem file (issue #91) — JavaScript thuần, không thư viện.
 *
 * Không nhúng thư viện lưới: điểm cuối `…/cells` đã trả sẵn từng CỬA SỔ ô, nên phần
 * một thư viện lưới làm hộ (cắt khung nhìn, dựng thanh cuộn) còn lại đúng hai phép
 * nhân, trong khi phần khó — hỏi cửa sổ theo vùng đang xem, màn chờ trích xuất, hai
 * công tắc — vẫn phải tự viết vì không thư viện nào biết hợp đồng dữ liệu này.
 *
 * Ô nằm ở lớp định vị tuyệt đối trong một khung cuộn: chiều cao khung = tổng dòng ×
 * chiều cao dòng, nên trang tính 243.464 dòng có thanh cuộn thật mà chỉ vài chục ô
 * nằm trong DOM. Số dòng và chữ cái cột là hai lớp riêng dịch theo `scrollLeft` /
 * `scrollTop` — dính mép mà không phụ thuộc `position: sticky` trên ô tuyệt đối.
 *
 * Màn chờ trích xuất: lượt trích xuất đầu của file 71,3MB mất 164,6 giây, quá biên
 * cắt 100 giây của Cloudflare. Máy chủ trả 202 kèm số dòng đã đọc; lưới hiện màn
 * chờ rồi tự hỏi lại với `wait=0` — cán bộ không phải bấm lại, và không request nào
 * giữ kết nối lâu.
 *
 * Hình dạng khai ra được (#123): điểm neo `#cell-grid` khai sẵn `role="table"` + tên +
 * `aria-rowcount` / `aria-colcount` ở TEMPLATE, còn đây đóng hai số thật vào khi cửa sổ
 * đầu về, và đóng vai cho từng phần lưới dựng ra. Dòng ô là phần tử THẬT (`.cg-row`),
 * không phải một biển ô phẳng: `role="row"` phải có ô nằm trong nó mới đọc ra được.
 * Vùng số dòng và ô góc mang `aria-hidden` — chúng lặp lại `aria-rowindex` bằng hình,
 * và là hai lớp cuộn riêng nên không nằm được trong dòng của chúng.
 */
(function () {
  'use strict';

  var ROW_H = 26;          // px mỗi dòng — cố định, để suy vị trí từ chỉ số dòng
  var COL_W = 148;
  var ROWNUM_W = 86;
  var HEAD_H = 32;          // một dòng: chữ cái cột + tên trường hệ thống đọc
  var HEAD_H_LABELLED = 48; // hai dòng: thêm nhãn của cột, thành CHỮ
  var ROW_MARGIN = 60;     // dòng nạp thừa mỗi phía, đủ cho một cú cuộn nhanh
  var COL_MARGIN = 8;
  var MAX_ROWS = 400;      // trần điểm cuối là 1000
  var MAX_COLS = 120;
  var POLL_MS = 2000;
  var POLL_MAX_TRIES = 400;  // ~13 phút; lượt 164,6 giây nằm gọn bên trong

  var SSML_NOTE =
    'Định dạng XML SpreadsheetML 2003: xem trước được, chưa nạp được. Bộ đọc dữ ' +
    'liệu chưa nhận định dạng này, nên file xem được ở lưới nhưng chưa vào số liệu.';
  var NO_MAP_NOTE =
    'Hệ thống chưa đọc file này lần nào nên chưa có cột nào để đánh dấu.';

  var state = {
    url: '', sheet: 0, parsedSheet: '', mapped: {},
    meta: null, win: null,
    showMapped: false, showFormula: false,
    highlight: [],
    tries: 0, timer: null, fetching: false, gen: 0,
    lastKey: '',
  };

  var el = {};

  function colLetter(i) {
    var s = '', x = i;
    for (;;) {
      s = String.fromCharCode(65 + (x % 26)) + s;
      x = Math.floor(x / 26) - 1;
      if (x < 0) return s;
    }
  }

  function intVi(n) {
    return new Intl.NumberFormat('vi-VN').format(n);
  }

  function cellText(rowIndex, colIndex) {
    var win = state.win;
    if (!win) return null;
    var r = rowIndex - win.rowStart;
    if (r < 0 || r >= win.rows.length) return null;
    if (state.showFormula && win.formulas && win.formulas[r]) {
      var f = win.formulas[r][String(colIndex)];
      if (f !== undefined) return { text: f, formula: true };
    }
    var c = colIndex - win.colStart;
    var row = win.rows[r];
    if (c < 0 || c >= row.length) return { text: '', formula: false };
    var v = row[c];
    if (v === null || v === undefined) return { text: '', formula: false };
    return { text: String(v), formula: false };
  }

  // ------------------------------------------------------------- khung ----

  function build(container) {
    container.textContent = '';
    el.root = container;
    // Khung là lớp ĐỊNH VỊ, không phải một phần của bảng: nó khai `presentation` để vai
    // thuộc về con nó (xem `document_file.html` cho quy tắc con của `role="table"`).
    var frame = document.createElement('div');
    frame.className = 'cg-frame';
    frame.setAttribute('role', 'presentation');

    // Ô góc chỉ có dấu `#`, và vùng số dòng lặp lại đúng `aria-rowindex` của mỗi dòng.
    // Cả hai là hình, nên giấu khỏi cây khả truy cập thay vì đọc lên hai lần.
    el.corner = document.createElement('div');
    el.corner.className = 'cg-corner';
    el.corner.textContent = '#';
    el.corner.setAttribute('aria-hidden', 'true');

    el.head = document.createElement('div');
    el.head.className = 'cg-head';
    el.head.setAttribute('role', 'rowgroup');
    el.headInner = document.createElement('div');
    el.headInner.className = 'cg-head-inner';
    el.headInner.setAttribute('role', 'row');
    el.head.appendChild(el.headInner);

    el.side = document.createElement('div');
    el.side.className = 'cg-side';
    el.side.setAttribute('aria-hidden', 'true');
    el.sideInner = document.createElement('div');
    el.sideInner.className = 'cg-side-inner';
    el.side.appendChild(el.sideInner);

    el.body = document.createElement('div');
    el.body.className = 'cg-body';
    el.body.setAttribute('role', 'rowgroup');
    el.canvas = document.createElement('div');
    el.canvas.className = 'cg-canvas';
    el.canvas.setAttribute('role', 'presentation');
    el.body.appendChild(el.canvas);

    // Màn chờ / màn lỗi do TEMPLATE dựng, nằm ngoài `#cell-grid` và chồng lên nó.
    el.overlay = document.getElementById('cg-overlay');

    frame.appendChild(el.corner);
    frame.appendChild(el.head);
    frame.appendChild(el.side);
    frame.appendChild(el.body);
    container.appendChild(frame);

    el.body.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', function () { render(true); });
  }

  function onScroll() {
    el.headInner.style.transform = 'translateX(' + -el.body.scrollLeft + 'px)';
    el.sideInner.style.transform = 'translateY(' + -el.body.scrollTop + 'px)';
    render(false);
  }

  function visibleRange() {
    var firstRow = Math.max(0, Math.floor(el.body.scrollTop / ROW_H));
    var nRows = Math.ceil(el.body.clientHeight / ROW_H) + 1;
    var firstCol = Math.max(0, Math.floor(el.body.scrollLeft / COL_W));
    var nCols = Math.ceil(el.body.clientWidth / COL_W) + 1;
    var total = state.meta || { total_rows: 0, total_cols: 0 };
    return {
      firstRow: firstRow,
      lastRow: Math.min(total.total_rows, firstRow + nRows),
      firstCol: firstCol,
      lastCol: Math.min(total.total_cols, firstCol + nCols),
    };
  }

  // ------------------------------------------------------------ vẽ lưới ----

  function onParsedSheet() {
    // Chú giải cột chỉ đúng trên trang parser đọc — trang khác thì không đánh dấu.
    return !(state.parsedSheet && state.meta && state.meta.sheet_name !== state.parsedSheet);
  }

  function markedColumn(colIndex) {
    if (!state.showMapped) return null;
    if (!onParsedSheet()) return null;
    return state.mapped[String(colIndex)] || null;
  }

  function isHighlighted(colIndex) {
    return state.highlight.indexOf(colIndex) !== -1 && onParsedSheet();
  }

  function columnHeader(colIndex) {
    // Tiêu đề cột là chỗ DUY NHẤT lưới nói "hệ thống đọc cột này thành trường gì", nên
    // nó phải đọc được bằng bàn phím và bằng trình đọc màn hình: `role="columnheader"`
    // để mỗi ô của cột được đọc kèm tên cột, `aria-colindex` vì lưới chỉ giữ vài chục
    // cột trong DOM nên vị trí không suy ra được từ thứ tự phần tử.
    var th = document.createElement('div');
    th.className = 'cg-col';
    th.setAttribute('role', 'columnheader');
    th.setAttribute('aria-colindex', String(colIndex + 1));
    th.style.left = (colIndex * COL_W) + 'px';

    var line = document.createElement('span');
    line.className = 'cg-col-line';
    var letter = document.createElement('span');
    letter.className = 'cg-col-letter';
    letter.textContent = colLetter(colIndex);
    line.appendChild(letter);

    var mark = markedColumn(colIndex);
    if (mark) {
      var tag = document.createElement('span');
      tag.className = 'cg-col-field';
      tag.textContent = mark.label;
      // `title` chỉ LẶP LẠI chữ đang hiện — bề ngang cột cắt tên trường dài, và chuột
      // đọc được phần bị cắt. Không thông tin nào chỉ có trong `title`.
      tag.title = mark.label;
      line.appendChild(tag);
    }
    th.appendChild(line);

    var labels = (mark && mark.labels) || [];
    if (mark) th.classList.add(labels.length ? 'cg-col-labelled' : 'cg-col-mapped');
    labels.forEach(function (lb) {
      // Nhãn dựng ở máy chủ từ CÙNG property dòng trường đọc (`BasisColumn.labels`),
      // nên lưới không có bộ từ vựng riêng — trục đi kèm chữ để khẳng định được.
      var label = document.createElement('span');
      label.className = 'cg-col-label';
      label.setAttribute('data-axis', lb.axis);
      label.textContent = lb.text;
      th.appendChild(label);
    });

    if (isHighlighted(colIndex)) th.classList.add('cg-col-hi');
    return th;
  }

  function render(force) {
    if (!state.meta) return;
    var v = visibleRange();
    var key = [v.firstRow, v.lastRow, v.firstCol, v.lastCol,
               state.showMapped, state.showFormula, state.highlight.join(','),
               state.win ? state.win.rowStart : -1,
               state.win ? state.win.colStart : -1].join(':');
    if (!force && key === state.lastKey) return;
    state.lastKey = key;

    el.canvas.style.width = (state.meta.total_cols * COL_W) + 'px';
    el.canvas.style.height = (state.meta.total_rows * ROW_H) + 'px';
    el.headInner.style.width = el.canvas.style.width;
    el.sideInner.style.height = el.canvas.style.height;

    var head = document.createDocumentFragment();
    for (var c = v.firstCol; c < v.lastCol; c++) {
      head.appendChild(columnHeader(c));
    }
    el.headInner.textContent = '';
    el.headInner.appendChild(head);

    var side = document.createDocumentFragment();
    var body = document.createDocumentFragment();
    for (var r = v.firstRow; r < v.lastRow; r++) {
      var num = document.createElement('div');
      num.className = 'cg-rownum';
      num.style.top = (r * ROW_H) + 'px';
      num.textContent = intVi(r + 1);
      side.appendChild(num);

      // Dòng là phần tử thật, ô nằm TRONG dòng: `role="row"` rỗng không đọc ra được gì,
      // và chỉ số dòng của trang tính nói MỘT lần ở đây thay vì lặp trên từng ô.
      var tr = document.createElement('div');
      tr.className = 'cg-row';
      tr.setAttribute('role', 'row');
      tr.setAttribute('aria-rowindex', String(r + 1));
      tr.style.top = (r * ROW_H) + 'px';

      for (var cc = v.firstCol; cc < v.lastCol; cc++) {
        var cell = document.createElement('div');
        cell.className = 'cg-cell';
        cell.setAttribute('role', 'cell');
        cell.setAttribute('aria-colindex', String(cc + 1));
        cell.style.left = (cc * COL_W) + 'px';
        var got = cellText(r, cc);
        if (got === null) {
          cell.classList.add('cg-cell-loading');
        } else {
          cell.textContent = got.text;
          if (got.text) cell.title = got.text;
          if (got.formula) cell.classList.add('cg-cell-formula');
        }
        if (markedColumn(cc)) cell.classList.add('cg-cell-mapped');
        if (isHighlighted(cc)) cell.classList.add('cg-cell-hi');
        tr.appendChild(cell);
      }
      body.appendChild(tr);
    }
    el.sideInner.textContent = '';
    el.sideInner.appendChild(side);
    el.canvas.textContent = '';
    el.canvas.appendChild(body);

    ensureWindow(v);
  }

  // ---------------------------------------------------------- lấy dữ liệu --

  function covers(v) {
    var w = state.win;
    if (!w) return false;
    return w.rowStart <= v.firstRow && v.lastRow <= w.rowStart + w.rows.length
      && w.colStart <= v.firstCol && v.lastCol <= w.colStart + w.width;
  }

  function ensureWindow(v) {
    if (covers(v) || state.fetching) return;
    var rowStart = Math.max(0, v.firstRow - ROW_MARGIN);
    var nRows = Math.min(MAX_ROWS, (v.lastRow - v.firstRow) + 2 * ROW_MARGIN);
    var colStart = Math.max(0, v.firstCol - COL_MARGIN);
    var nCols = Math.min(MAX_COLS, (v.lastCol - v.firstCol) + 2 * COL_MARGIN);
    load({ row: rowStart, rows: nRows, col: colStart, cols: nCols });
  }

  function windowUrl(range, wait) {
    var p = new URLSearchParams();
    p.set('sheet', String(state.sheet));
    p.set('row', String(range.row));
    p.set('rows', String(Math.max(1, range.rows)));
    p.set('col', String(range.col));
    p.set('cols', String(Math.max(1, range.cols)));
    if (state.showFormula) p.set('formulas', '1');
    if (wait !== undefined) p.set('wait', String(wait));
    return state.url + '?' + p.toString();
  }

  function load(range, opts) {
    opts = opts || {};
    // Mỗi lượt hỏi mang một số thứ tự; trả lời của lượt đã bị vượt thì BỎ. Không
    // có nó thì một lượt 202 về muộn đè màn chờ lên lưới đã dựng xong.
    var gen = ++state.gen;
    state.fetching = true;
    if (state.timer) { clearTimeout(state.timer); state.timer = null; }
    fetch(windowUrl(range, opts.wait), { credentials: 'same-origin' })
      .then(function (r) {
        return r.json().then(function (data) { return { status: r.status, data: data }; });
      })
      .then(function (res) {
        if (gen !== state.gen) return;
        state.fetching = false;
        if (res.status === 202) { onExtracting(res.data, range); return; }
        if (res.status !== 200) { showError(res.data); return; }
        onWindow(res.data, range);
      })
      .catch(function () {
        // Lỗi mạng là tạm thời — hỏi lại, không đổi trạng thái lưới.
        if (gen !== state.gen) return;
        state.fetching = false;
        state.timer = setTimeout(function () { load(range, { wait: 0 }); }, POLL_MS);
      });
  }

  function onWindow(data, range) {
    state.tries = 0;
    state.meta = data;
    state.win = {
      rowStart: data.row_start,
      colStart: data.col_start,
      width: range.cols,
      rows: data.rows || [],
      formulas: data.formulas || null,
    };
    hideOverlay();
    renderNotes(data);
    renderStatus(data);
    setDimensions(data);
    applyHeadHeight();
    if (data.total_rows === 0) {
      showCard('Trang tính này không có ô nào.', '');
      return;
    }
    render(true);
  }

  function onExtracting(data, range) {
    if (++state.tries > POLL_MAX_TRIES) {
      showError({ detail: 'Lượt trích xuất chạy quá lâu. Hãy mở lại trang.' });
      return;
    }
    showWait(data);
    state.timer = setTimeout(function () { load(range, { wait: 0 }); }, POLL_MS);
  }

  // ----------------------------------------------------------- thẻ trạng thái --

  function showCard(title, body, cls) {
    el.overlay.hidden = false;
    el.overlay.className = 'cg-overlay' + (cls ? ' ' + cls : '');
    el.overlay.textContent = '';
    var h = document.createElement('p');
    h.className = 'cg-overlay-title';
    h.textContent = title;
    el.overlay.appendChild(h);
    if (body) {
      var p = document.createElement('p');
      p.className = 'cg-overlay-body';
      p.textContent = body;
      el.overlay.appendChild(p);
    }
    return el.overlay;
  }

  function hideOverlay() {
    el.overlay.hidden = true;
  }

  function showWait(data) {
    var card = showCard(
      'Đang trích xuất file để dựng lưới',
      'Đây là lần đầu mở trang tính này. Hệ thống đang đọc trọn trang vào kho đệm; '
        + 'các lần mở sau hiện ngay, kể cả khi nhảy tới dòng cuối. '
        + 'Trang tự cập nhật, không cần bấm lại.',
      'cg-overlay-wait',
    );
    var line = document.createElement('p');
    line.className = 'cg-overlay-progress';
    line.textContent = 'Đã đọc ' + intVi(data.rows_done || 0) + ' dòng · '
      + (Math.round((data.elapsed_ms || 0) / 100) / 10).toFixed(1).replace('.', ',') + ' giây';
    card.appendChild(line);
    var bar = document.createElement('div');
    bar.className = 'cg-bar';
    bar.appendChild(document.createElement('span'));
    card.appendChild(bar);
  }

  function showError(data) {
    var detail = (data && data.detail) || 'Không đọc được file.';
    var card = showCard('Không dựng được lưới', detail, 'cg-overlay-error');
    if (data && data.format_label) {
      var p = document.createElement('p');
      p.className = 'cg-overlay-body';
      p.textContent = 'Định dạng dò được: ' + data.format_label + '.';
      card.appendChild(p);
    }
  }

  // ------------------------------------------------------ thanh trên lưới --

  function wireSheetPicker() {
    // Bộ chọn trang tính dựng ở MÁY CHỦ (#124), không dựng ở đây nữa: hai chỗ dựng cùng
    // một danh sách là hai chỗ đi lệch nhau.
    //
    // Liên kết `?sheet=N`, không phải nút: địa chỉ là thứ nói trang nào đang xem, nên
    // không có JS thì cú bấm tải lại trang và máy chủ dựng đúng trang đó. Ở đây chỉ chặn
    // cú bấm để đổi tại chỗ, vì lưới đã nằm sẵn trong trang.
    var links = document.querySelectorAll('.js-sheet-pick');
    Array.prototype.forEach.call(links, function (a) {
      a.addEventListener('click', function (ev) {
        // Bấm mở tab mới / cửa sổ mới vẫn phải là mở tab mới.
        if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey || ev.button) return;
        ev.preventDefault();
        openSheet(parseInt(a.dataset.sheetIndex, 10) || 0, a.dataset.sheetName || '');
      });
    });
  }

  function markSheet(index) {
    var links = document.querySelectorAll('.js-sheet-pick');
    Array.prototype.forEach.call(links, function (a) {
      var on = Number(a.dataset.sheetIndex) === index;
      a.classList.toggle('btn-primary', on);
      a.classList.toggle('btn-secondary', !on);
      if (on) a.setAttribute('aria-current', 'true');
      else a.removeAttribute('aria-current');
    });
  }

  function setPinTarget(name) {
    // Nút ghim luôn trỏ vào trang ĐANG XEM. Cái ghim KHÔNG tự chạy theo khung nhìn: nó
    // chỉ đổi khi cán bộ bấm nút, và biểu mẫu gán cột không mang ô trang tính nên một
    // lượt xác nhận cột cũng không dời được nó.
    var pin = document.getElementById('sheet-pin');
    if (!pin) return;
    pin.value = name;
    var label = document.getElementById('sheet-pin-name');
    if (label) label.textContent = name;
    // Ghim lại đúng trang đang ghim không đổi một dòng nào — `disabled` thay vì xếp
    // một lượt nạp lại toàn kỳ.
    pin.disabled = !name || name === (pin.dataset.pinned || '');
  }

  function revealSettings(name) {
    // Mở vùng cài đặt khi cán bộ xem sang một trang KHÁC trang hệ thống đọc: đó là trạng
    // thái duy nhất nút ghim có việc để làm, và nút đó nằm trong vùng. Máy chủ đã mở sẵn
    // cho lượt tải lại (`ReadSettings.viewing_other`); đây là đường của lượt đổi tại chỗ,
    // vì đổi tại chỗ không dựng lại trang.
    //
    // Chỉ MỞ, không đóng lại: cán bộ tự mở ra thì lượt đổi trang sau không được đóng lại
    // thứ họ đang đọc.
    var box = document.getElementById('read-settings');
    if (box && name && name !== state.parsedSheet) box.open = true;
  }

  function openSheet(index, name) {
    if (index === state.sheet) return;
    state.sheet = index;
    state.meta = null;
    state.win = null;
    state.lastKey = '';
    el.body.scrollTop = 0;
    el.body.scrollLeft = 0;
    onScroll();
    markSheet(index);
    setPinTarget(name || '');
    revealSettings(name || '');
    var u = new URL(window.location.href);
    u.searchParams.set('sheet', String(index));
    window.history.replaceState({}, '', u.toString());
    showCard('Đang mở trang tính…', '');
    load({ row: 0, rows: 200, col: 0, cols: 60 });
  }

  function note(text, cls) {
    var p = document.createElement('p');
    p.className = 'cg-note' + (cls ? ' ' + cls : '');
    p.textContent = text;
    return p;
  }

  function renderNotes(data) {
    var box = document.getElementById('cg-notes');
    if (!box) return;
    box.textContent = '';
    if (data.format === 'spreadsheetml') box.appendChild(note(SSML_NOTE, 'cg-note-warn'));
    if (state.showFormula && data.formulas_supported === false) {
      // `.xls` cũ: nói thẳng là không đọc được công thức, lưới vẫn giữ giá trị thật.
      box.appendChild(note(data.formula_note || '', 'cg-note-warn'));
    }
    if (state.showMapped) {
      var hasMap = Object.keys(state.mapped).length > 0;
      if (!hasMap) {
        box.appendChild(note(NO_MAP_NOTE));
      } else if (state.parsedSheet && data.sheet_name !== state.parsedSheet) {
        box.appendChild(note(
          'Cột hệ thống đọc nằm ở trang tính “' + state.parsedSheet + '”, trang đang xem là “'
            + data.sheet_name + '” — không đánh dấu ở đây.', 'cg-note-warn'));
      }
    }
  }

  function setDimensions(data) {
    // Hai số này là số của TRANG TÍNH, đúng hai số dòng trạng thái dưới lưới viết ra
    // ("12.345 dòng × 20 cột") và đúng hai khoá `total_rows` / `total_cols` của payload
    // lưới. Lấy số khác thì trang đọc lên một số và viết ra một số khác cho cùng file.
    //
    // Hàng chữ cái cột KHÔNG tính vào `aria-rowcount` và không mang `aria-rowindex`:
    // tính nó thì `aria-rowindex` của mọi dòng dữ liệu lệch 1 so với số dòng đang hiện
    // ở lề trái, mà ở trang tính thì số dòng CHÍNH LÀ danh tính của dòng.
    el.root.setAttribute('aria-rowcount', String(data.total_rows));
    el.root.setAttribute('aria-colcount', String(data.total_cols));
  }

  function anyColumnLabelled() {
    // Chỉ tính cột lưới THẬT SỰ vẽ ra: vị trí đã lưu trỏ được ra ngoài trang tính (map
    // giữ cột 8 trong khi trang tính có 8 cột, chỉ số 0..7), và nới tiêu đề cho một cột
    // không bao giờ hiện là chừa một dòng trống suốt lượt xem.
    var total = state.meta ? state.meta.total_cols : 0;
    var marks = state.mapped;
    for (var key in marks) {
      if (!Object.prototype.hasOwnProperty.call(marks, key)) continue;
      if (Number(key) < total && (marks[key].labels || []).length) return true;
    }
    return false;
  }

  function applyHeadHeight() {
    // Nhãn của cột chiếm DÒNG THỨ HAI của tiêu đề, và chỉ khi có nhãn để hiện: bề ngang
    // một cột là 148px, nhét nhãn cạnh tên trường thì cả hai cùng bị cắt. Thiếu bước này
    // thì nhãn vẫn nằm trong DOM nhưng `overflow: hidden` của tiêu đề cắt mất.
    //
    // Đo trên CẢ bản đồ cột chứ không trên khung nhìn — theo khung nhìn thì chiều cao
    // tiêu đề nhảy trong lúc cuộn ngang.
    var tall = state.showMapped && onParsedSheet() && anyColumnLabelled();
    document.documentElement.style.setProperty(
      '--cg-head-h', (tall ? HEAD_H_LABELLED : HEAD_H) + 'px');
  }

  function renderStatus(data) {
    var box = document.getElementById('cg-status');
    if (!box) return;
    var parts = [
      intVi(data.total_rows) + ' dòng × ' + intVi(data.total_cols) + ' cột',
      data.format_label,
    ];
    if (data.from_cache) {
      parts.push('lấy từ kho đệm xem trước');
    } else {
      parts.push('trích xuất lần đầu mất '
        + (Math.round((data.build_ms || 0) / 100) / 10).toFixed(1).replace('.', ',') + ' giây');
    }
    box.textContent = parts.join(' · ');
  }

  // ------------------------------------------------------------ khởi động --

  function showColumn(index) {
    // Cuộn NGANG tới cột đang soi, không đụng vị trí dòng: cán bộ đang đối chiếu
    // đúng những dòng trước mắt, kéo họ về dòng 1 là bắt tìm lại.
    //
    // Cùng điều kiện với `isHighlighted`: chỉ số cột chỉ có nghĩa trên trang tính parser
    // đọc. Cuộn mà không đánh dấu được gì thì lưới dời đi vì một lý do không hiện ra.
    if (!onParsedSheet()) return;
    if (!state.meta || index >= state.meta.total_cols) return;
    var left = index * COL_W;
    var view = el.body.scrollLeft;
    if (left < view || left + COL_W > view + el.body.clientWidth) {
      el.body.scrollLeft = Math.max(0, left - COL_W);
      onScroll();
    }
  }

  function setHighlight(raw) {
    // Ô nhập của nhóm cột con chứa CẢ NHÓM (`7,8`) và dòng trường nói ra cả nhóm ("cột 7
    // · «…» + cột 8 · «…»"): trường đó đọc bằng TỔNG các cột (ADR #25). Soi mỗi cột đầu
    // thì lưới nói ngược lại chính dòng đang gõ, nên làm nổi cả nhóm.
    var next = [];
    String(raw === null || raw === undefined ? '' : raw).split(/[,\s;]+/).forEach(function (part) {
      var idx = parseInt(part, 10);
      if (!isNaN(idx) && idx >= 0 && next.indexOf(idx) === -1) next.push(idx);
    });
    if (next.join(',') === state.highlight.join(',')) return;
    state.highlight = next;
    render(true);
    // Cuộn tới cột ĐẦU nhóm. Nhóm cột con thường liền nhau nên một cú cuộn là thấy cả
    // nhóm; map đã lưu vẫn giữ được nhóm rải rộng hơn khung nhìn, và ở đó không cú cuộn
    // nào thấy hết — cột đầu là mốc để cán bộ đọc tiếp sang phải.
    if (next.length) showColumn(next[0]);
  }

  function wireColumnPickers() {
    // Biểu mẫu xác nhận cột nằm CÙNG TRANG với lưới đầy đủ (#92): chọn một cột thì đúng
    // cột đó sáng lên trong lưới, thay cho lưới rút gọn 15 dòng của màn cũ.
    //
    // Bộ chọn là LỚP TRẦN, không có tiền tố thẻ: từ #121 dòng cột đơn dùng `<select>` còn
    // dòng nhóm cột con dùng ô nhập, nên `input.…` (dạng cũ) bỏ sót một nửa số dòng — và
    // `querySelectorAll` trả rỗng thì cả chuỗi chết mà không ném lỗi nào.
    var picks = document.querySelectorAll('.js-col-pick');
    Array.prototype.forEach.call(picks, function (pick) {
      function onPick() { setHighlight(pick.value); }
      pick.addEventListener('input', onPick);   // ô nhập chỉ số
      pick.addEventListener('change', onPick);  // `<select>`
      pick.addEventListener('focus', onPick);
      pick.addEventListener('blur', function () { setHighlight(''); });
    });
  }

  function wireControls() {
    var input = document.getElementById('cg-row-input');
    var go = document.getElementById('cg-row-go');
    function jump() {
      if (!state.meta || !input) return;
      var n = parseInt(input.value, 10);
      if (isNaN(n) || n < 1) return;
      n = Math.min(n, state.meta.total_rows);
      el.body.scrollTop = (n - 1) * ROW_H;
      onScroll();
    }
    if (go) go.addEventListener('click', jump);
    if (input) {
      input.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') { ev.preventDefault(); jump(); }
      });
    }

    var mapped = document.getElementById('cg-toggle-mapped');
    if (mapped) {
      mapped.addEventListener('change', function () {
        state.showMapped = mapped.checked;
        if (state.meta) renderNotes(state.meta);
        applyHeadHeight();
        render(true);
      });
    }

    wireColumnPickers();
    wireSheetPicker();

    var formula = document.getElementById('cg-toggle-formula');
    if (formula) {
      formula.addEventListener('change', function () {
        state.showFormula = formula.checked;
        if (state.meta) renderNotes(state.meta);
        // Bật: công thức là dữ liệu THÊM của cửa sổ nên phải hỏi lại đúng cửa sổ
        // đang xem. Tắt: giá trị đã có sẵn trong cửa sổ, vẽ lại là đủ.
        if (state.showFormula) state.win = null;
        state.lastKey = '';
        render(true);
      });
    }
  }

  function init() {
    var container = document.getElementById('cell-grid');
    if (!container) return;
    state.url = container.dataset.cellsUrl || '';
    state.sheet = parseInt(container.dataset.sheet || '0', 10) || 0;
    state.parsedSheet = container.dataset.parsedSheet || '';
    try {
      state.mapped = JSON.parse(container.dataset.mappedColumns || '{}');
    } catch (e) {
      state.mapped = {};
    }
    if (!state.url) return;

    build(container);
    wireControls();
    document.documentElement.style.setProperty('--cg-row-h', ROW_H + 'px');
    document.documentElement.style.setProperty('--cg-col-w', COL_W + 'px');
    document.documentElement.style.setProperty('--cg-rownum-w', ROWNUM_W + 'px');
    applyHeadHeight();
    showCard('Đang mở file…', '');
    load({ row: 0, rows: 200, col: 0, cols: 60 });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
