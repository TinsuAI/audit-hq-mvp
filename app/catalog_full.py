"""Catalog đầy đủ 49 kiểm tra theo §4 đề án Audit-HQ.

Đây là snapshot từ `de-an-audit-hq.md` §4 — source of truth duy nhất.
Khi đề án bump version, đồng bộ tay file này. Trang `/danh-muc-kiem-tra`
đọc trực tiếp, không qua DB.

Đối lập với `app/checks/registry.py` (17 check đã implement runnable),
file này liệt kê toàn bộ 49 dự kiến, bao gồm WIP + conditional.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    phase: int                # 1 hoặc 2
    group: int                # 1..12
    code: str                 # vd "C4.3"
    title: str                # mô tả ngắn vấn đề (dùng làm tiêu đề)
    problem: str              # mô tả vấn đề / công thức
    risk: str                 # rủi ro nghiệp vụ
    severities: tuple[str, ...]   # ("warning",) hoặc ("warning","critical") — theo Mức cột bảng
    status: str               # "mvp" | "wip" | "conditional"


GROUP_NAMES: dict[int, str] = {
    1: "Số lượng nhập / xuất",
    2: "Cân bằng và tồn kho",
    3: "Phân loại hàng hoá",
    4: "Định mức M16",
    5: "Truy nguồn nguyên vật liệu nhập khẩu",
    6: "Kiểm tra liên kỳ",
    7: "So sánh giữa các doanh nghiệp",
    8: "Phế liệu và phế phẩm",
    9: "Sản phẩm dở dang (bán thành phẩm)",
    10: "Đối chiếu sổ sách kế toán",
    11: "TSCĐ, máy móc và năng lực vận hành",
    12: "Nhà cung cấp",
}

GROUP_NOTE: dict[int, str] = {
    6: "Cần dữ liệu ≥2 kỳ BCQT.",
    7: "Kích hoạt khi cơ quan Hải quan đã có đủ doanh nghiệp trong danh mục (≥30 doanh nghiệp cùng ngành).",
    8: "Dữ liệu doanh nghiệp cần cung cấp thêm: sổ kho phế liệu, hoá đơn bán phế liệu nội địa, danh mục A42 đã nộp cho phế liệu.",
    9: "Dữ liệu doanh nghiệp cần cung cấp thêm: sổ kho bán thành phẩm, sổ sản xuất, sơ đồ công đoạn, định mức từng tầng BTP.",
    10: "Dữ liệu doanh nghiệp cần cung cấp thêm: Bảng cân đối phát sinh, sổ chi tiết 152/155/156, Báo cáo tài chính kỳ tương ứng.",
    11: "Dữ liệu doanh nghiệp cần cung cấp thêm: danh mục tài sản cố định (sổ TSCĐ), báo cáo cơ sở sản xuất, hồ sơ máy móc nhập khẩu miễn thuế.",
    12: "Điều kiện kích hoạt: trường nhà cung cấp trong BCCT đã chuẩn hoá; bảng tham chiếu định dạng MST quốc gia xuất xứ; danh sách nhà cung cấp rủi ro do cơ quan Hải quan cung cấp.",
}

STATUS_LABEL: dict[str, str] = {
    "mvp": "Đã triển khai",
    "wip": "Bổ sung thí điểm",
    "conditional": "Cần thêm điều kiện",
}

STATUS_ICON: dict[str, str] = {
    "mvp": "✅",
    "wip": "🚧",
    "conditional": "⏳",
}

SEVERITY_ICON: dict[str, str] = {
    "critical": "🔴",
    "warning": "🟡",
    "info": "🔵",
}


CATALOG: list[CatalogEntry] = [
    # --- Nhóm 1 — Số lượng nhập / xuất ---
    CatalogEntry(
        phase=1, group=1, code="C1.1",
        title="Lệch số lượng nhập nguyên vật liệu (M15 vs tờ khai)",
        problem="`nhập_trong_kỳ` (M15) khác Σ tờ khai nhập theo mã. Loại hình: DNCX E11+E15 / Gia công E21+E23 / SXXK E31+E33. Ngưỡng: <5% Thông tin · 5–20% Cảnh báo · >20% Nghiêm trọng.",
        risk="Khai thiếu hoặc khai thừa nhập khẩu.",
        severities=("warning",), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=1, code="C1.2",
        title="Có tờ khai nhập nhưng không có trong M15",
        problem="Mã có trên BCCT nhưng không có dòng trong M15. Đánh dấu mọi trường hợp.",
        risk="Bỏ sót nguyên vật liệu nhập khẩu khỏi BCQT.",
        severities=("critical",), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=1, code="C1.3",
        title="Có trong M15 nhưng không có tờ khai",
        problem="`nhập_trong_kỳ` > 0 mà không có tờ khai tương ứng.",
        risk="M15 không có căn cứ tờ khai; doanh nghiệp có thể \"mượn\" mã NVL nhập khẩu để hợp thức hoá hàng mua nội địa không hoá đơn hoặc hàng nhập khẩu không khai báo, đưa vào phạm vi miễn thuế.",
        severities=("critical",), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=1, code="C1.4",
        title="Lệch số lượng xuất thành phẩm (M15a vs tờ khai)",
        problem="`xuất_khẩu` khác Σ tờ khai xuất theo mã thành phẩm. Loại hình: DNCX E42 / Gia công E52 / SXXK E62. Ngưỡng: <1% Thông tin · 1–5% Cảnh báo · >5% Nghiêm trọng.",
        risk="Khai sai sản lượng xuất khẩu — khai khống để giảm lượng NVL miễn thuế phải giải trình, hoặc khai thiếu để giấu nguồn thu.",
        severities=("warning",), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=1, code="C1.5",
        title="Tái xuất M15 không có tờ khai B13",
        problem="`xuất_trả_lại` > 0 trong M15 nhưng không có B13 tương ứng.",
        risk="Ghi tái xuất để giảm tồn nhưng không có tờ khai chứng minh.",
        severities=("warning",), status="wip",
    ),
    CatalogEntry(
        phase=1, group=1, code="C1.6",
        title="Chuyển mục đích sử dụng không có tờ khai A42",
        problem="`chuyển_mục_đích_sử_dụng` > 0 nhưng không có A42.",
        risk="Hàng miễn thuế chuyển nội địa không khai báo — vi phạm điều kiện miễn thuế.",
        severities=("critical",), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=1, code="C1.7",
        title="Tỷ lệ chuyển mục đích sử dụng vượt ngưỡng",
        problem="`chuyển_mục_đích_sử_dụng / (tồn_đầu_kỳ + nhập_trong_kỳ)` cao bất thường. Ngưỡng: ≥10% Cảnh báo · ≥25% Nghiêm trọng.",
        risk="Doanh nghiệp lợi dụng kẽ hở miễn thuế — nhập NVL miễn thuế rồi chuyển nội địa với tỷ lệ cao, biến đặc quyền miễn thuế thành kênh nhập hàng tiêu thụ nội địa.",
        severities=("warning", "critical"), status="mvp",
    ),
    # --- Nhóm 2 — Cân bằng và tồn kho ---
    CatalogEntry(
        phase=1, group=2, code="C2.1",
        title="Mất cân bằng phương trình M15 (NVL)",
        problem="`tồn_cuối ≠ tồn_đầu + nhập − xuất_trả − xuất_SX − chuyển_MĐSD − xuất_khác` (tolerance ±0,01). Trường hợp tồn ảo: tồn_đầu = 0 nhưng tồn_cuối > nhập_trong_kỳ.",
        risk="Báo cáo không đáng tin cậy về mặt số học. Tồn ảo gợi ý \"tồn kho ảo\" để treo nợ thuế — doanh nghiệp thực tế đã tiêu thụ nhưng báo cáo vẫn để tồn để không nộp thuế nhập khẩu.",
        severities=("critical",), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=2, code="C2.2",
        title="Mất cân bằng phương trình M15a (TP)",
        problem="`tồn_cuối ≠ tồn_đầu + nhập_kho − chuyển_MĐSD − xuất_khẩu − xuất_khác`.",
        risk="Báo cáo cân đối thành phẩm không đáng tin cậy về mặt số học.",
        severities=("critical",), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=2, code="C2.3",
        title="Tồn cuối âm — nguyên vật liệu (M15)",
        problem="`tồn_cuối_kỳ` < 0 trên bất kỳ mã nào.",
        risk="Bỏ sót tờ khai nhập khẩu, sử dụng NVL không khai báo, hoặc điều chỉnh số liệu tồn kho sai thực tế.",
        severities=("critical",), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=2, code="C2.4",
        title="Tồn cuối âm — thành phẩm (M15a)",
        problem="`tồn_cuối_kỳ` < 0 trên bất kỳ mã nào.",
        risk="Tương tự C2.3 cho thành phẩm — bỏ sót tờ khai, sử dụng hàng không khai báo, hoặc điều chỉnh tồn kho sai thực tế.",
        severities=("critical",), status="mvp",
    ),
    # --- Nhóm 3 — Phân loại hàng hoá ---
    CatalogEntry(
        phase=1, group=3, code="C3.1",
        title="Cùng mã vật tư khai nhiều loại hình mâu thuẫn",
        problem="Một mã có trên cả tờ khai NVL và tờ khai MMTB trong cùng kỳ. Cặp mâu thuẫn: E11+E13 · E31+E13 · E21+E13.",
        risk="Phân loại sai dẫn đến sai phạm vi BCQT.",
        severities=("warning",), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=3, code="C3.2",
        title="Mã HS không nhất quán trong kỳ",
        problem="Cùng mã vật tư có ≥2 mã HS khác nhau. Khác phân nhóm (6 số) Thông tin · khác nhóm (4 số) Cảnh báo · khác chương (2 số) Nghiêm trọng.",
        risk="Cố ý thay đổi mã HS để né chính sách quản lý chuyên ngành (kiểm tra chất lượng, kiểm dịch) hoặc để hưởng thuế suất ưu đãi đặc biệt bất hợp pháp.",
        severities=("warning", "critical"), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=3, code="C3.3",
        title="Đơn vị tính không nhất quán (cùng mã vật tư)",
        problem="≥2 đơn vị khác nhau giữa M15 và BCCT.",
        risk="Sai đơn vị tính ×1000 khiến toàn bộ nhập/xuất/tồn sai hệ thống.",
        severities=("critical",), status="mvp",
    ),
    # --- Nhóm 4 — Định mức M16 ---
    CatalogEntry(
        phase=1, group=4, code="C4.1",
        title="NVL trong M16 không có nhập khẩu và không có tồn đầu kỳ",
        problem="`mã_NVL` trong M16 nhưng (không có dòng trong M15) HOẶC (cả `nhập_trong_kỳ` = 0 VÀ `tồn_đầu_kỳ` = 0). Loại trừ NVL còn tồn từ kỳ trước.",
        risk="NVL xuất hiện trong định mức nhưng không có nguồn nhập khẩu lẫn tồn đầu — không thể giải trình dòng vật tư từ tờ khai đến TP xuất khẩu.",
        severities=("critical",), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=4, code="C4.2",
        title="Thành phẩm trong M16 không có trong M15a",
        problem="`mã_SP_xuất_khẩu` trong M16 nhưng không có dòng trong M15a.",
        risk="Định mức cho TP không có trong báo cáo xuất khẩu.",
        severities=("warning",), status="wip",
    ),
    CatalogEntry(
        phase=1, group=4, code="C4.3",
        title="Tổng tiêu hao M16 vượt xuất sản xuất M15",
        problem="Σ(`định_mức` × `sản_lượng_sản_xuất_M15a`) theo NVL > `xuất_sản_xuất` trong M15. Vượt >5% Cảnh báo · >20% Nghiêm trọng. Mã NVL không có dòng nào trong M15 thuộc C4.1 (thiếu nguồn), không xét ở đây.",
        risk="Cách phổ biến nhất để lấy NVL miễn thuế ra bán nội địa — định mức ảo gồm cả thành phần không có thực trong sản phẩm, thổi phồng tiêu hao để hợp thức hoá NVL nhập khẩu dư.",
        severities=("warning", "critical"), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=4, code="C4.4",
        title="M16 phân mảnh: nhiều NVL cùng chức năng cho một thành phẩm",
        problem="Ví dụ: 1 áo có 10 loại cúc khác nhau trong M16. Phát hiện qua (A) ≥N mã cùng HS 4 số / TP, (B) gom nhóm tên gần giống, (C) Hải quan định nghĩa nhóm vật tư. Ngưỡng: ≥5 cùng HS / TP Cảnh báo · ≥10 Nghiêm trọng.",
        risk="Phân mảnh NVL để che số lượng, hợp thức hoá nhập khẩu dư.",
        severities=("warning",), status="wip",
    ),
    CatalogEntry(
        phase=1, group=4, code="C4.5",
        title="Định mức bằng 0 hoặc âm",
        problem="`định_mức_thực_tế` ≤ 0 trên bất kỳ dòng M16 nào.",
        risk="Lỗi dữ liệu hoặc cố tình khai 0 để che tiêu hao thực tế.",
        severities=("critical",), status="wip",
    ),
    CatalogEntry(
        phase=1, group=4, code="C4.6",
        title="Định mức bất thường cao (ngoại lai thống kê)",
        problem="`định_mức` cặp TP-NVL kỳ N vượt xa trung bình của chính cặp đó qua các kỳ trước. Vượt trung bình ±3σ Cảnh báo · ±5σ Nghiêm trọng. Yêu cầu: ≥3 kỳ BCQT.",
        risk="Thổi phồng định mức để hợp thức hoá NVL nhập khẩu vượt mức.",
        severities=("warning",), status="wip",
    ),
    CatalogEntry(
        phase=1, group=4, code="C4.7",
        title="Phân bổ định mức bất thường (mở rộng từ C4.4)",
        problem="(a) Cùng cặp TP-NVL có nhiều định mức khác nhau cùng kỳ; (b) một NVL dùng cho quá nhiều TP không liên quan; (c) một TP có số lượng dòng NVL vượt ngưỡng hợp lý của ngành.",
        risk="Phân mảnh / điều chỉnh / nguỵ tạo định mức để chế số liệu quyết toán thay vì phản ánh tiêu hao thực tế.",
        severities=("warning", "critical"), status="wip",
    ),
    CatalogEntry(
        phase=1, group=4, code="C4.8",
        title="Tồn NVL âm tại một thời điểm trong kỳ (cộng dồn)",
        problem="`tồn_đầu_kỳ + Σ(nhập NVL đến thời điểm t) − Σ(định_mức × TP xuất khẩu đến thời điểm t)` ở từng tháng/quý. Âm tại bất kỳ thời điểm nào → cảnh báo.",
        risk="Định mức M16 khai cao bất thường (lý do chính), hoặc khai thừa TP xuất khẩu, hoặc khai thiếu nhập NVL. Doanh nghiệp \"sản xuất nhiều hơn nguyên liệu thực có\" trên giấy tờ.",
        severities=("critical",), status="wip",
    ),
    # --- Nhóm 5 — Truy nguồn NVL nhập khẩu ---
    CatalogEntry(
        phase=1, group=5, code="C5.1",
        title="NVL có xuất sản xuất trong M15 nhưng không có nhập khẩu",
        problem="M15 có `xuất_sản_xuất` > 0 và `nhập_trong_kỳ` = 0 và `tồn_đầu_kỳ` = 0.",
        risk="Tiêu hao từ nguồn không khai báo — NVL nội địa bị đưa vào phạm vi miễn thuế.",
        severities=("critical",), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=5, code="C5.2",
        title="Thành phẩm xuất khẩu không có trong M16 (TP mồ côi)",
        problem="Mã TP có `xuất_khẩu` > 0 trong M15a nhưng không có dòng M16.",
        risk="Không thể giải trình NVL đầu vào cho TP đã xuất khẩu; doanh nghiệp có thể dùng nguyên liệu không rõ nguồn gốc (kể cả hàng lậu) để sản xuất xuất khẩu.",
        severities=("warning",), status="wip",
    ),
    CatalogEntry(
        phase=1, group=5, code="C5.3",
        title="Tỷ lệ truy nguồn thấp theo mã NVL",
        problem="Σ(`định_mức` × `xuất_khẩu_M15a`) / (`xuất_sản_xuất_M15` − NVL còn ở BTP và TP tồn cuối kỳ). <80% Cảnh báo · <60% Nghiêm trọng. Không áp dụng cho DN có TP bán nội địa lớn hoặc nhiều tầng BTP tự sản xuất (dùng Nhóm 9).",
        risk="Phần lớn NVL nhập khẩu không truy được vào TP xuất khẩu cụ thể.",
        severities=("warning",), status="wip",
    ),
    # --- Nhóm 6 — Liên kỳ ---
    CatalogEntry(
        phase=1, group=6, code="C6.1",
        title="Tồn đầu kỳ N khác tồn cuối kỳ N-1 — NVL (M15)",
        problem="Theo từng mã NVL, tolerance ±0,01.",
        risk="Điều chỉnh tồn giữa 2 kỳ không có giải trình.",
        severities=("critical",), status="mvp",
    ),
    CatalogEntry(
        phase=1, group=6, code="C6.2",
        title="Tồn đầu kỳ N khác tồn cuối kỳ N-1 — TP (M15a)",
        problem="Tương tự C6.1 cho thành phẩm.",
        risk="Điều chỉnh tồn giữa 2 kỳ không có giải trình.",
        severities=("critical",), status="wip",
    ),
    CatalogEntry(
        phase=1, group=6, code="C6.3",
        title="Định mức M16 thay đổi đột biến giữa các kỳ",
        problem="Chênh lệch tỷ lệ giữa định mức kỳ N và N-1 (cùng cặp TP-NVL). >20% Cảnh báo · >50% Nghiêm trọng.",
        risk="Thổi phồng hoặc co định mức để điều tiết lượng NVL cần giải trình.",
        severities=("warning",), status="wip",
    ),
    CatalogEntry(
        phase=1, group=6, code="C6.4",
        title="Nhập tăng mạnh nhưng xuất khẩu không tăng tương ứng",
        problem="Nhập tăng >50% trong khi xuất tăng <10% → Cảnh báo.",
        risk="Tích luỹ tồn NVL bất thường, nguy cơ chuyển nội địa không khai báo A42. **Cảnh báo đặc biệt:** doanh nghiệp sắp giải thể, bỏ trốn — tranh thủ nhập miễn thuế rồi tẩu tán trước khi đóng MST.",
        severities=("warning",), status="wip",
    ),
    CatalogEntry(
        phase=1, group=6, code="C6.5",
        title="Mã HS thay đổi cho cùng mã vật tư giữa các kỳ",
        problem="Đổi nhóm (4 số) Cảnh báo · đổi chương (2 số) Nghiêm trọng.",
        risk="Phân loại lại để chuyển sang nhóm thuế suất hoặc chính sách có lợi hơn.",
        severities=("warning", "critical"), status="wip",
    ),
    # --- Nhóm 7 — So sánh giữa các DN ---
    CatalogEntry(
        phase=1, group=7, code="C7.1",
        title="Định mức bất thường so với cùng ngành",
        problem="Định mức doanh nghiệp vượt trung bình ngành (cùng chương HS hoặc cùng loại sản phẩm) một khoảng lớn.",
        risk="Định mức cao bất thường so với mặt bằng cùng ngành.",
        severities=("warning",), status="conditional",
    ),
    CatalogEntry(
        phase=1, group=7, code="C7.2",
        title="Giá nhập từ cùng nhà cung cấp chênh lệch giữa các DN",
        problem="Cùng nhà cung cấp, cùng mã HS, giá khác nhau lớn giữa các doanh nghiệp.",
        risk="Chuyển giá hoặc trốn thuế có hệ thống.",
        severities=("warning", "critical"), status="conditional",
    ),
    CatalogEntry(
        phase=1, group=7, code="C7.3",
        title="Lượng nhập/xuất cùng mã HS bất thường so với ngành",
        problem="Vượt xa giá trị trung vị của ngành.",
        risk="Quy mô bất thường cần kiểm tra.",
        severities=("warning",), status="conditional",
    ),
    # --- Nhóm 8 — Phế liệu / phế phẩm ---
    CatalogEntry(
        phase=2, group=8, code="C8.1",
        title="Tỷ lệ phế liệu / phế phẩm thực tế vượt ngưỡng ngành",
        problem="Cặp NVL-TP có tỷ lệ phế thải vượt trung bình ngành. Ngưỡng theo từng ngành (kim loại, dệt may, điện tử, hoá chất…) do Hải quan định nghĩa.",
        risk="Khai phế liệu cao để giảm lượng NVL cần giải trình hoặc che tiêu thụ nội địa.",
        severities=("warning",), status="conditional",
    ),
    CatalogEntry(
        phase=2, group=8, code="C8.2",
        title="Phế liệu bán nội địa không có tờ khai A42",
        problem="Doanh nghiệp ghi nhận bán phế liệu trong sổ sách nhưng không có A42 tương ứng.",
        risk="Vi phạm điều kiện miễn thuế — phế liệu phát sinh từ NVL miễn thuế, bán nội địa phải khai A42 và nộp thuế.",
        severities=("critical",), status="conditional",
    ),
    CatalogEntry(
        phase=2, group=8, code="C8.3",
        title="Tỷ lệ phế liệu thay đổi đột biến giữa các kỳ",
        problem="Tỷ lệ phế thải kỳ N cao bất thường so với N-1 (cùng dây chuyền).",
        risk="Điều tiết phế liệu để cân đối số liệu tồn kho qua các kỳ.",
        severities=("warning",), status="conditional",
    ),
    # --- Nhóm 9 — BTP ---
    CatalogEntry(
        phase=2, group=9, code="C9.1",
        title="BTP đa tầng không truy nguồn được về NVL gốc",
        problem="BTP cấp 1, 2, 3… thiếu định mức chi tiết từng tầng hoặc thiếu liên kết về NVL ban đầu. Yêu cầu DN cung cấp định mức từng tầng BTP và sơ đồ công đoạn.",
        risk="Làm mờ truy nguồn — NVL đã nhập khẩu \"nằm\" trong BTP nhiều tầng, đối chiếu với TP xuất khẩu không còn tuyến tính.",
        severities=("warning",), status="conditional",
    ),
    CatalogEntry(
        phase=2, group=9, code="C9.2",
        title="Tồn BTP cuối kỳ N khác tồn BTP đầu kỳ N+1",
        problem="Biến động không có giải trình.",
        risk="BTP bị \"đẩy qua lại\" giữa các kỳ để điều chỉnh tồn kho mà không thay đổi dòng thực tế.",
        severities=("warning",), status="conditional",
    ),
    CatalogEntry(
        phase=2, group=9, code="C9.3",
        title="Tồn BTP lớn không tương xứng với năng lực sản xuất",
        problem="`tồn_BTP_cuối_kỳ` × thời gian gia công TB > năng lực dây chuyền × số ngày sản xuất trong kỳ. Yêu cầu báo cáo cơ sở sản xuất.",
        risk="Che giấu tiêu thụ nội địa — NVL đã đưa vào BTP nhưng thực tế bị tiêu thụ / bán nội địa, khó phát hiện vì chưa \"ra TP\".",
        severities=("warning",), status="conditional",
    ),
    CatalogEntry(
        phase=2, group=9, code="C9.4",
        title="Cấu thành NVL của BTP không khớp định mức vs sổ kho",
        problem="Định mức tầng BTP tính ra khác lượng NVL đã xuất kho cho BTP đó.",
        risk="Tách nhỏ một quy trình thành nhiều tầng BTP để làm loãng sai lệch định mức, tạo vùng xám dễ lợi dụng.",
        severities=("critical",), status="conditional",
    ),
    # --- Nhóm 10 — Sổ sách kế toán ---
    CatalogEntry(
        phase=2, group=10, code="C10.1",
        title="Tồn kho BCQT khác số dư TK 152/155/156 trên BCĐ phát sinh",
        problem="Đối chiếu tồn kho đầu/cuối kỳ BCQT với số dư các tài khoản 152 (NVL), 155 (TP), 156 (Hàng hoá).",
        risk="Số liệu BCQT không khớp sổ sách kế toán — hai nguồn số liệu mâu thuẫn cần làm rõ.",
        severities=("critical",), status="conditional",
    ),
    CatalogEntry(
        phase=2, group=10, code="C10.2",
        title="Doanh thu xuất khẩu sổ kế toán khác trị giá xuất khẩu BCCT",
        problem="Đối chiếu cùng kỳ. <2% Thông tin · 2–5% Cảnh báo · >5% Nghiêm trọng. Lưu ý: doanh thu KT theo giá thanh toán, BCCT theo giá hải quan (FOB), chênh nhẹ hợp lệ.",
        risk="Khai sai một trong hai phía, ảnh hưởng nghĩa vụ thuế TNDN hoặc thuế xuất khẩu.",
        severities=("warning", "critical"), status="conditional",
    ),
    CatalogEntry(
        phase=2, group=10, code="C10.3",
        title="Giá trị nhập khẩu sổ kế toán khác trị giá nhập khẩu BCCT",
        problem="Đối chiếu cùng kỳ. <2% Thông tin · 2–5% Cảnh báo · >5% Nghiêm trọng. Chênh lệch nhẹ có thể hợp lệ do tỷ giá ghi sổ kế toán khác tỷ giá hải quan.",
        risk="Khai sai một trong hai phía hoặc có nguồn nhập không khai báo.",
        severities=("warning", "critical"), status="conditional",
    ),
    # --- Nhóm 11 — TSCĐ, MMTB ---
    CatalogEntry(
        phase=2, group=11, code="C11.1",
        title="MMTB miễn thuế (E13) không khớp danh mục báo cáo cơ sở SX",
        problem="Đối chiếu danh mục máy móc miễn thuế nhập khẩu với báo cáo cơ sở sản xuất.",
        risk="Máy móc miễn thuế đã bán nội địa, chuyển nhượng, hoặc đưa ra khỏi cơ sở mà không khai báo.",
        severities=("critical",), status="conditional",
    ),
    CatalogEntry(
        phase=2, group=11, code="C11.2",
        title="Công suất máy móc không khớp sản lượng thực tế BCQT",
        problem="Tổng `nhập_kho_M15a` chia cho công suất danh nghĩa khai báo. <50% hoặc >150% → Cảnh báo. >200% → Nghiêm trọng (vượt năng lực = nhập từ nguồn khác).",
        risk="Khai báo công suất không trung thực để được miễn thuế (khai cao khi nhập) hoặc hợp thức hoá lượng xuất khẩu vượt năng lực (gia công thuê ngoài / nhập lậu).",
        severities=("warning",), status="conditional",
    ),
    CatalogEntry(
        phase=2, group=11, code="C11.3",
        title="Tồn kho cuối kỳ bất thường so với năng lực vận hành",
        problem="Giá trị tồn NVL/TP cuối kỳ vượt sức chứa kho khai báo hoặc vượt vốn lưu động bình quân trên BCTC cùng kỳ. Vượt 50% Cảnh báo · 100% Nghiêm trọng.",
        risk="Tồn kho ảo — hàng đã thực tế tiêu thụ hoặc bán nội địa nhưng vẫn duy trì số tồn để treo nợ thuế nhập khẩu. Pattern điển hình của DNCX sắp giải thể hoặc muốn tránh đối chiếu tồn thực tế.",
        severities=("critical",), status="conditional",
    ),
    # --- Nhóm 12 — Nhà cung cấp ---
    CatalogEntry(
        phase=2, group=12, code="C12.1",
        title="Nhà cung cấp mới xuất hiện đột ngột chiếm tỷ trọng lớn",
        problem="Nhà cung cấp chưa từng xuất hiện trong các kỳ trước nhưng kỳ này chiếm >30% kim ngạch nhập.",
        risk="Nhà cung cấp giả lập (công ty ma), hoặc thay đổi nhà cung cấp để né kiểm soát chuyển giá / xuất xứ.",
        severities=("warning",), status="conditional",
    ),
    CatalogEntry(
        phase=2, group=12, code="C12.2",
        title="Mã số thuế / thông tin nhà cung cấp không hợp lệ",
        problem="Định dạng MST sai, nhà cung cấp trên tờ khai không khớp dạng định danh quốc tế của nước xuất xứ.",
        risk="Nhà cung cấp không có thật, hoặc khai mượn danh nhà cung cấp khác.",
        severities=("critical",), status="conditional",
    ),
    CatalogEntry(
        phase=2, group=12, code="C12.3",
        title="Nhà cung cấp nằm trong danh sách rủi ro",
        problem="Đối chiếu với danh sách nhà cung cấp nghi vấn (chuyển giá, gian lận xuất xứ, đã bị xử phạt) do Hải quan cung cấp.",
        risk="Doanh nghiệp tiếp tục giao dịch với nhà cung cấp đã được Hải quan đánh dấu rủi ro.",
        severities=("warning", "critical"), status="conditional",
    ),
]


def summary_counts() -> dict[str, int]:
    """Đếm tổng + theo status cho hero band."""
    counts = {"total": len(CATALOG), "mvp": 0, "wip": 0, "conditional": 0}
    for e in CATALOG:
        counts[e.status] += 1
    return counts


def grouped_by_phase() -> list[dict]:
    """Trả về list 2 phase, mỗi phase có list group, mỗi group có entries."""
    out: dict[int, dict[int, list[CatalogEntry]]] = {1: {}, 2: {}}
    for e in CATALOG:
        out[e.phase].setdefault(e.group, []).append(e)
    phases = [
        {"phase": 1, "title": "Giai đoạn I — TKXNK + BCQT (Hải quan đã có dữ liệu)",
         "subtitle": "Chạy ngay trên dữ liệu Hải quan đã có sẵn, không yêu cầu doanh nghiệp cung cấp thêm."},
        {"phase": 2, "title": "Giai đoạn II — Mở rộng, cần dữ liệu bổ sung",
         "subtitle": "Yêu cầu doanh nghiệp cung cấp thêm sổ sách / báo cáo cơ sở SX / danh mục tài sản. Triển khai sau khi Giai đoạn I ổn định."},
    ]
    for p in phases:
        p["groups"] = [
            {
                "group": g,
                "name": GROUP_NAMES[g],
                "note": GROUP_NOTE.get(g),
                "entries": out[p["phase"]][g],
            }
            for g in sorted(out[p["phase"]].keys())
        ]
    return phases
