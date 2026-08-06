"""Nửa do LLM viết của tổng quan: JSON bốn mục + hậu kiểm số (ADR #21 mục 3-4).

Model chỉ ĐỌC bảng số liệu đã tính (TQ-3) rồi trả bốn trường ngắn. Mọi con số
trong nhận định phải COPY NGUYÊN CHUỖI đã định dạng sẵn trong prompt; hậu kiểm
so khớp CHUỖI chứ không parse số — parse vấp làm tròn (61,8 → 62%), năm 2025, mã
kiểm tra C1.6, và mã hàng có chữ số.

Lệch → gắn cờ `cần đối chiếu` + badge, KHÔNG publish âm thầm. Đây là bộ dò
hallucination rẻ nhất hệ thống chạy được, đặt đúng trên artifact ra trước mặt
khách.
"""

from __future__ import annotations

import json
import re

MIN_FINDINGS_FOR_DISTRIBUTION = 10
MAX_HOTSPOTS = 5
MAX_SUGGESTIONS = 3

SECTION_KEYS = ("nhan_dinh", "phan_bo", "diem_nong", "de_xuat")

SYSTEM_PROMPT = (
    "Bạn là trợ lý kiểm toán cho cán bộ Hải quan Việt Nam. Bạn được cấp một BẢNG SỐ "
    "LIỆU đã tính sẵn cho MỘT kiểm tra của một doanh nghiệp trong một năm. Nhiệm vụ "
    "duy nhất: đọc bảng đó và viết nhận định ngắn bằng tiếng Việt trang trọng.\n\n"
    "TRẢ VỀ JSON THUẦN (không markdown, không ```), đúng các khoá sau:\n"
    '{"nhan_dinh": "1–2 câu", "phan_bo": "2–3 câu", '
    '"diem_nong": [{"subject_key": "...", "nhan_xet": "1 câu"}], '
    '"de_xuat": ["...", "..."]}\n\n'
    "Quy tắc bắt buộc:\n"
    "- MỌI con số bạn viết phải COPY NGUYÊN VĂN từ bảng số liệu. Không làm tròn, "
    "không đổi đơn vị, không tự tính thêm số mới.\n"
    "- KHÔNG bịa mã hàng: `subject_key` chỉ lấy từ danh sách mã trong bảng.\n"
    f"- `diem_nong` tối đa {MAX_HOTSPOTS} mục, `de_xuat` tối đa {MAX_SUGGESTIONS} mục.\n"
    "- KHÔNG khẳng định 'sạch' hay 'không vi phạm'. Đây là chỉ số rủi ro DỮ LIỆU.\n"
    "- KHÔNG viết câu miễn trừ trách nhiệm — giao diện đã có sẵn."
)


def _fmt(value: float | int) -> str:
    """Định dạng số kiểu Việt Nam (dấu phẩy thập phân) — đúng chuỗi model phải copy."""
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def build_prompt_payload(stats: dict, company_name: str) -> tuple[str, set[str]]:
    """`(khối text cấp cho model, tập chuỗi được phép xuất hiện trong nhận định)`.

    Cấp sẵn số ĐÃ ĐỊNH DẠNG để model chỉ việc copy — nếu bắt model tự định dạng
    thì hậu kiểm so chuỗi sẽ báo lệch trên mọi khác biệt trình bày.
    """
    lines: list[str] = []
    allowed: set[str] = set()

    def add(label: str, value: str) -> None:
        lines.append(f"- {label}: {value}")
        allowed.add(value)

    lines.append(f"Doanh nghiệp: {company_name}")
    lines.append(f"Kiểm tra: {stats['check_code']} — {stats.get('title', '')}")
    lines.append(f"Năm: {stats['year']}")
    allowed.update({stats["check_code"], str(stats["year"])})

    total = stats["total_findings"]
    add("Tổng số phát hiện", _fmt(total))
    sev = stats["severity_totals"]
    add("Nghiêm trọng", _fmt(sev["critical"]))
    add("Cảnh báo", _fmt(sev["warning"]))
    add("Thông tin", _fmt(sev["info"]))

    conc = stats["concentration"]
    add("Số mã liên quan", _fmt(conc["distinct_subjects"]))
    add("Tỉ trọng 5 mã lớn nhất (%)", _fmt(conc["top5_share_pct"]))
    add("Số mã phủ 80% số phát hiện", _fmt(conc["subjects_covering_80pct"]))
    if conc["top_subjects"]:
        lines.append("- Mã nhiều phát hiện nhất:")
        for s in conc["top_subjects"]:
            lines.append(f"  · {s['subject_key']}: {_fmt(s['count'])} phát hiện")
            allowed.add(s["subject_key"])
            allowed.add(_fmt(s["count"]))

    for nf in stats.get("numeric_fields", []):
        unit = "%" if nf["is_pct"] else ""
        lines.append(f"- Trường `{nf['key']}` trên {_fmt(nf['n'])} mã:")
        for label, key in (
            ("thấp nhất", "min"), ("trung vị", "p50"), ("phân vị 90", "p90"), ("cao nhất", "max")
        ):
            v = f"{_fmt(nf[key])}{unit}"
            lines.append(f"  · {label}: {v}")
            allowed.add(v)
            allowed.add(_fmt(nf[key]))
        lines.append(
            f"  · cao hơn: {_fmt(nf['higher'])} mã · thấp hơn: {_fmt(nf['lower'])} mã"
        )
        allowed.update({_fmt(nf["n"]), _fmt(nf["higher"]), _fmt(nf["lower"])})

    for b in stats.get("by_book", []):
        add(f"Sổ {b['label']}", _fmt(b["count"]))

    prev = stats["previous_year"]
    if prev.get("available"):
        add(f"Tổng phát hiện năm {prev['year']}", _fmt(prev["total"]))
        add("Chênh lệch so với năm trước", f"{prev['delta']:+d}")
        add("Số mã mới xuất hiện", _fmt(prev["new_subjects_count"]))
        allowed.add(str(prev["year"]))
        allowed.update(prev.get("new_subjects", []))
    else:
        lines.append(
            f"- Không có dữ liệu năm {prev['year']} để so sánh. KHÔNG được viết là 0."
        )
        allowed.add(str(prev["year"]))

    if total < MIN_FINDINGS_FOR_DISTRIBUTION:
        lines.append(
            f"- Kiểm tra này chỉ có {_fmt(total)} phát hiện: BỎ TRỐNG trường `phan_bo`."
        )

    block = "\n".join(lines)
    # Được phép copy MỌI con số xuất hiện trong bảng, kể cả trong nhãn ("5 mã lớn
    # nhất", "phủ 80%", "phân vị 90"). Model được bảo copy từ bảng, mà bảng chính
    # là khối này — chỉ nhận riêng phần giá trị sẽ gắn cờ nhầm những câu đúng.
    allowed.add(block)
    return block, allowed


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _tokens(text: str) -> set[str]:
    return set(_NUMBER.findall(text or ""))


def unsupported_numbers(sections: dict, allowed: set[str]) -> list[str]:
    """Con số trong nhận định KHÔNG khớp chuỗi nào của bảng số liệu.

    So khớp trên TOKEN số, hai bên cùng cách tách, nên "61,8%" trong bảng khớp
    "61,8" trong câu. Không parse: parse vấp làm tròn, năm, mã kiểm tra và mã
    hàng có chữ số.
    """
    allowed_tokens = _tokens(" ".join(allowed))
    written: set[str] = set()
    written |= _tokens(sections.get("nhan_dinh", ""))
    written |= _tokens(sections.get("phan_bo", ""))
    for h in sections.get("diem_nong") or []:
        written |= _tokens(str(h.get("subject_key", "")))
        written |= _tokens(str(h.get("nhan_xet", "")))
    for s in sections.get("de_xuat") or []:
        written |= _tokens(str(s))
    return sorted(written - allowed_tokens)


def _first_json_object(text: str) -> str | None:
    """Đối tượng `{…}` cân ngoặc ĐẦU TIÊN trong `text`, bỏ câu dẫn / ghi chú quanh nó.

    Đếm ngoặc chứ không regex: giá trị chuỗi trong JSON có thể chứa `{` `}`. Bỏ qua
    ngoặc nằm trong chuỗi và ký tự bị escape.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None  # cụt giữa chừng (chạm max_tokens) — đừng đoán phần thiếu


def parse_sections(raw: str) -> dict | None:
    """JSON bốn mục từ phản hồi model. None nếu không parse được → xuống cấp text thô.

    Chịu được hai kiểu model hay trả sai dù prompt đã dặn:

    - **Ký tự điều khiển thô trong chuỗi.** `json.loads` mặc định `strict=True` từ
      chối xuống dòng / tab thật bên trong chuỗi. Model xuống dòng giữa một câu dài
      là parse trượt, trong khi `white-space: pre-wrap` render ra y hệt JSON hợp lệ —
      nhìn màn hình không thấy được lỗi. Dùng `strict=False`.
    - **Chữ thừa quanh JSON.** Câu dẫn trước `{`, ghi chú sau `}`, hoặc rào ```json
      không bọc trọn chuỗi. Cắt lấy đối tượng cân ngoặc đầu tiên.
    """
    if not raw:
        return None
    text = raw.strip()
    # Model hay bọc ```json … ``` dù đã bảo đừng.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1)

    data = None
    for candidate in (text, _first_json_object(text)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate, strict=False)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            break
        data = None
    if not isinstance(data, dict):
        return None

    hotspots = []
    for h in (data.get("diem_nong") or [])[:MAX_HOTSPOTS]:
        if isinstance(h, dict) and h.get("subject_key"):
            hotspots.append({
                "subject_key": str(h["subject_key"]),
                "nhan_xet": str(h.get("nhan_xet", "")),
            })
    return {
        "nhan_dinh": str(data.get("nhan_dinh") or "").strip(),
        "phan_bo": str(data.get("phan_bo") or "").strip(),
        "diem_nong": hotspots,
        "de_xuat": [str(s).strip() for s in (data.get("de_xuat") or [])[:MAX_SUGGESTIONS] if s],
    }


def finalize_sections(sections: dict | None, stats: dict, allowed: set[str]) -> tuple[dict | None, list[str]]:
    """Áp quy tắc trình bày + hậu kiểm số. Trả `(sections, số_không_khớp)`."""
    if sections is None:
        return None, []
    if stats["total_findings"] < MIN_FINDINGS_FOR_DISTRIBUTION:
        # Đoạn phân bố cho 7 dòng là độn chữ — bỏ, kể cả khi model vẫn viết.
        sections["phan_bo"] = ""
    # Mã hàng model bịa ra: chỉ giữ mã có trong bảng số liệu.
    known = {s["subject_key"] for s in stats["concentration"]["top_subjects"]}
    known |= set(stats["previous_year"].get("new_subjects") or [])
    sections["diem_nong"] = [h for h in sections["diem_nong"] if h["subject_key"] in known]
    return sections, unsupported_numbers(sections, allowed)
