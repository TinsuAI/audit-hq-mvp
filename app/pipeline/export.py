"""Xuất báo cáo Excel kiến nghị kiểm tra (§6.3 đề án — "Xuất báo cáo").

Workbook gồm các sheet:
    1. Tổng quan       — info DN + tổng findings theo severity + ranking
    2. Phát hiện       — danh sách mọi finding (mã, severity, đối tượng, mô tả)
    3. Chứng cứ M15    — các NvlBalance liên quan đến findings
    4. Chứng cứ M15a   — các SpBalance liên quan
    5. Chứng cứ M16    — các Norm liên quan
    6. Chứng cứ BCCT   — các DeclarationLine liên quan
    7. Pháp lý         — trích yếu TT 39/2018, TT 38/2015...
"""

from __future__ import annotations

from io import BytesIO

import xlsxwriter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks.combos import COMBO_SPECS
from app.checks.registry import SEVERITY_LABEL_VI, SPECS
from app.models import Company, DeclarationLine, Finding, Norm, NvlBalance, SpBalance

_LEGAL_REFERENCES = [
    (
        "Thông tư 39/2018/TT-BTC",
        "Quy định về thủ tục hải quan; kiểm tra, giám sát hải quan; thuế xuất khẩu, "
        "thuế nhập khẩu và quản lý thuế đối với hàng hoá XNK.",
    ),
    (
        "Thông tư 38/2015/TT-BTC",
        "Quy định thủ tục hải quan, kiểm tra giám sát; thuế XNK; "
        "quản lý thuế đối với hàng hoá XNK.",
    ),
    (
        "Nghị định 134/2016/NĐ-CP",
        "Quy định chi tiết một số điều và biện pháp thi hành Luật Thuế xuất khẩu, nhập khẩu.",
    ),
    (
        "Luật Hải quan 54/2014/QH13",
        "Quy định quản lý nhà nước về hải quan đối với hàng hoá xuất khẩu, "
        "nhập khẩu, quá cảnh.",
    ),
    (
        "Quyết định 1357/QĐ-TCHQ",
        "Ban hành Bảng mã loại hình XNK và hướng dẫn sử dụng.",
    ),
]


def _severity_format(workbook: xlsxwriter.Workbook) -> dict:
    base = {"bold": True, "border": 1}
    return {
        "critical": workbook.add_format({**base, "bg_color": "#fce4e4", "font_color": "#8b1a1a"}),
        "warning": workbook.add_format({**base, "bg_color": "#fff4cc", "font_color": "#6e5300"}),
        "info": workbook.add_format({**base, "bg_color": "#e3f0fd", "font_color": "#1c4e80"}),
    }


def _write_overview(
    wb: xlsxwriter.Workbook, ws, company: Company, year: int, findings: list[Finding],
) -> None:
    bold = wb.add_format({"bold": True})
    title = wb.add_format({
        "bold": True, "font_size": 14, "bg_color": "#b22222", "font_color": "white",
    })
    label = wb.add_format({"bold": True, "bg_color": "#f0f0f0", "border": 1})
    cell = wb.add_format({"border": 1})

    ws.set_column("A:A", 30)
    ws.set_column("B:B", 50)
    ws.merge_range("A1:B1", "BÁO CÁO KIẾN NGHỊ KIỂM TRA", title)
    ws.set_row(0, 26)

    rows = [
        ("Doanh nghiệp", company.code),
        ("Tên DN", company.name or "—"),
        ("MST", company.tax_id or "—"),
        ("Địa chỉ", company.address or "—"),
        ("Kỳ báo cáo", str(year)),
        ("Điểm rủi ro DN", company.risk_score),
    ]
    for i, (k, v) in enumerate(rows, start=3):
        ws.write(f"A{i}", k, label)
        ws.write(f"B{i}", v, cell)

    sev_totals = {"critical": 0, "warning": 0, "info": 0}
    for f in findings:
        if f.status == "rejected":
            continue
        if f.severity in sev_totals:
            sev_totals[f.severity] += 1

    sev_rows = [
        ("Tổng số phát hiện", len(findings), bold),
        ("  Nghiêm trọng (🔴)", sev_totals["critical"], cell),
        ("  Cảnh báo (🟡)", sev_totals["warning"], cell),
        ("  Thông tin (🔵)", sev_totals["info"], cell),
    ]
    for i, (k, v, fmt) in enumerate(sev_rows, start=10):
        ws.write(f"A{i}", k, fmt)
        ws.write(f"B{i}", v, cell if fmt is cell else None)

    ws.write("A15", "Tham chiếu pháp lý chính", bold)
    ws.write("A16", "Mục", label)
    ws.write("B16", "Nội dung", label)
    for i, (key, desc) in enumerate(_LEGAL_REFERENCES[:3], start=17):
        ws.write(f"A{i}", key, cell)
        ws.write(f"B{i}", desc, cell)


def _write_findings(wb: xlsxwriter.Workbook, ws, findings: list[Finding]) -> None:
    sev_fmt = _severity_format(wb)
    header = wb.add_format({"bold": True, "bg_color": "#333333", "font_color": "white", "border": 1})
    cell = wb.add_format({"border": 1})
    title_cell = wb.add_format({"border": 1, "text_wrap": True})

    columns = ["Mã check", "Mức độ", "Nhóm", "Đối tượng", "Tiêu đề", "Trạng thái", "Ghi chú cán bộ"]
    widths = [12, 14, 8, 18, 60, 12, 30]
    for col, (name, w) in enumerate(zip(columns, widths, strict=True)):
        ws.write(0, col, name, header)
        ws.set_column(col, col, w)
    ws.set_row(0, 22)

    for row_idx, f in enumerate(findings, start=1):
        is_combo = f.check_code.startswith("COMBO_")
        spec = COMBO_SPECS.get(f.check_code) if is_combo else SPECS.get(f.check_code)
        group = "combo" if is_combo else (str(spec.group) if spec else "?")

        sev_format = sev_fmt.get(f.severity, cell)
        ws.write(row_idx, 0, f.check_code, cell)
        ws.write(row_idx, 1, SEVERITY_LABEL_VI.get(f.severity, f.severity), sev_format)
        ws.write(row_idx, 2, group, cell)
        ws.write(row_idx, 3, f.subject_key or "", cell)
        ws.write(row_idx, 4, f.title, title_cell)
        ws.write(row_idx, 5, f.status, cell)
        ws.write(row_idx, 6, f.notes or "", cell)


def _write_table(wb: xlsxwriter.Workbook, ws, rows: list, columns: list[str]) -> None:
    header = wb.add_format({"bold": True, "bg_color": "#f0f0f0", "border": 1})
    cell = wb.add_format({"border": 1})
    for col, name in enumerate(columns):
        ws.write(0, col, name, header)
        ws.set_column(col, col, max(12, min(40, len(name) + 2)))

    for row_idx, r in enumerate(rows, start=1):
        for col, name in enumerate(columns):
            v = getattr(r, name, None)
            if v is None:
                ws.write(row_idx, col, "", cell)
            else:
                ws.write(row_idx, col, v, cell)


def _write_legal(wb: xlsxwriter.Workbook, ws) -> None:
    header = wb.add_format({
        "bold": True, "bg_color": "#333333", "font_color": "white", "border": 1,
    })
    cell = wb.add_format({"border": 1, "text_wrap": True})
    ws.set_column("A:A", 30)
    ws.set_column("B:B", 80)
    ws.write("A1", "Văn bản", header)
    ws.write("B1", "Trích yếu", header)
    for i, (key, desc) in enumerate(_LEGAL_REFERENCES, start=2):
        ws.write(f"A{i}", key, cell)
        ws.write(f"B{i}", desc, cell)


def build_export(session: Session, company: Company, year: int) -> bytes:
    findings = session.scalars(
        select(Finding)
        .where(Finding.company_id == company.id, Finding.period_year == year)
        .order_by(Finding.check_code, Finding.subject_key)
    ).all()

    # Subject codes referenced by findings to filter evidence sheets.
    nvl_codes = {f.subject_key for f in findings if f.subject_type == "material_code" and f.subject_key}
    sp_codes = {f.subject_key for f in findings if f.subject_type == "product_code" and f.subject_key}
    item_codes = {f.subject_key for f in findings if f.subject_type == "item_code" and f.subject_key}
    all_codes_for_decl = nvl_codes | sp_codes | item_codes

    nvls = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company.id,
            NvlBalance.period_year == year,
            NvlBalance.material_code.in_(nvl_codes) if nvl_codes else NvlBalance.material_code.is_not(None),
        )
    ).all() if nvl_codes else []

    sps = session.scalars(
        select(SpBalance).where(
            SpBalance.company_id == company.id,
            SpBalance.period_year == year,
            SpBalance.product_code.in_(sp_codes) if sp_codes else SpBalance.product_code.is_not(None),
        )
    ).all() if sp_codes else []

    norms = session.scalars(
        select(Norm).where(
            Norm.company_id == company.id,
            Norm.period_year == year,
            Norm.material_code.in_(nvl_codes) if nvl_codes else Norm.material_code.is_not(None),
        )
    ).all() if nvl_codes else []

    if all_codes_for_decl:
        decls = session.scalars(
            select(DeclarationLine).where(
                DeclarationLine.company_id == company.id,
                DeclarationLine.period_year == year,
                DeclarationLine.item_code.in_(all_codes_for_decl),
            ).limit(500)
        ).all()
    else:
        decls = []

    buffer = BytesIO()
    wb = xlsxwriter.Workbook(buffer, {"in_memory": True})

    _write_overview(wb, wb.add_worksheet("Tổng quan"), company, year, findings)
    _write_findings(wb, wb.add_worksheet("Phát hiện"), findings)
    _write_table(
        wb, wb.add_worksheet("Chứng cứ M15"), nvls,
        ["material_code", "material_name", "unit", "opening_qty", "import_qty",
         "reexport_qty", "repurpose_qty", "production_out_qty", "other_out_qty", "closing_qty"],
    )
    _write_table(
        wb, wb.add_worksheet("Chứng cứ M15a"), sps,
        ["product_code", "product_name", "unit", "opening_qty", "intake_qty",
         "repurpose_qty", "export_qty", "other_out_qty", "closing_qty"],
    )
    _write_table(
        wb, wb.add_worksheet("Chứng cứ M16"), norms,
        ["product_code", "product_name", "material_code", "material_name", "material_unit", "norm_qty"],
    )
    _write_table(
        wb, wb.add_worksheet("Chứng cứ BCCT"), decls,
        ["declaration_no", "declaration_date", "customs_code", "item_code", "hs_code",
         "item_name", "origin", "quantity", "unit", "value_total", "partner"],
    )
    _write_legal(wb, wb.add_worksheet("Pháp lý"))

    wb.close()
    return buffer.getvalue()


def build_query_export(
    session: Session, sql: str, title: str | None = None, row_cap: int = 5000,
) -> bytes:
    """Xuất Excel TÙY BIẾN từ một câu SQL chỉ-đọc (kết quả query_sql).

    File tự-tài-liệu: hiển thị câu SQL đã chạy + kết quả + ghi chú truy nguồn
    (không hộp đen). Raise ValueError nếu SQL bị guard từ chối / lỗi chạy.
    """
    from app.ai.sql_tool import run_query

    res = run_query(session, sql, row_cap=row_cap)
    if "error" in res:
        raise ValueError(res["error"])
    cols: list[str] = res["columns"]
    rows: list[dict] = res["rows"]
    ncols = max(1, len(cols))

    buffer = BytesIO()
    wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
    ws = wb.add_worksheet("Kết quả")

    title_fmt = wb.add_format({
        "bold": True, "font_size": 13, "bg_color": "#1e40af", "font_color": "white",
    })
    label_fmt = wb.add_format({"bold": True, "bg_color": "#f0f0f0", "border": 1})
    sql_fmt = wb.add_format({
        "font_name": "Consolas", "text_wrap": True, "valign": "top", "border": 1,
    })
    header_fmt = wb.add_format({
        "bold": True, "bg_color": "#333333", "font_color": "white", "border": 1,
    })
    cell_fmt = wb.add_format({"border": 1})
    note_fmt = wb.add_format({"italic": True, "font_color": "#6b7280", "text_wrap": True})

    ws.merge_range(0, 0, 0, ncols - 1, title or "Báo cáo tùy biến — Audit-HQ", title_fmt)
    ws.set_row(0, 24)
    ws.write(1, 0, "Câu truy vấn đã chạy:", label_fmt)
    ws.merge_range(2, 0, 2, ncols - 1, res.get("sql", sql), sql_fmt)
    ws.set_row(2, 56)

    start = 4
    for c, name in enumerate(cols):
        ws.write(start, c, name, header_fmt)
        ws.set_column(c, c, max(12, min(48, len(str(name)) + 4)))
    for r, row in enumerate(rows, start=start + 1):
        for c, name in enumerate(cols):
            v = row.get(name)
            ws.write(r, c, "" if v is None else v, cell_fmt)

    note_row = start + 1 + len(rows) + 1
    note = f"{len(rows)} dòng"
    if res.get("truncated"):
        note += f" (đã đạt giới hạn {row_cap} — có thể còn thêm)"
    note += (
        " · Đây là chỉ số rủi ro dữ liệu BCQT, không phải kết luận tuân thủ pháp luật. "
        "AI có thể tạo thông tin sai — hãy đối chiếu nguồn gốc trước khi sử dụng."
    )
    ws.merge_range(note_row, 0, note_row, ncols - 1, note, note_fmt)

    wb.close()
    return buffer.getvalue()
