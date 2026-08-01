# DN_005 (Takagi) — trạng thái đã nạp + việc còn lại

> Bối cảnh: 2026-08-02, nạp gấp một DN mới lên prod (`audit-hq-demo`) để có bản demo.
> DN giữ **2 sổ quyết toán**: SXXK (E31/E62) và thuê gia công ở nước ngoài (E82/E41).
> Niên độ 01/04/2025–31/03/2026. Nạp **thẳng vào DB**, không qua đường upload.
> Trạng thái: dữ liệu + kiểm tra ĐÃ CHẠY trên prod, nhưng **code chưa vào main** —
> xem §4. Session này KHÔNG viết `.ai/STATUS.md` và không có session summary.

## 1. Đang có gì trên prod

Host `tinsu`, container `audit-hq-mvp`, DB `/db-data/audit_hq.sqlite`.

- `DN_005` · slug `cong-nghiep-nam-phong` · tên **"Công ty TNHH Công nghiệp Nam Phong" = TÊN GIẢ**.
  MST `0900321101` và địa chỉ là **số thật** (chủ ý, theo yêu cầu chỉ đổi tên) → tên giả
  nhưng vẫn truy ra được DN.
- `company_periods` 2025: `2025-04-01 → 2026-03-31`, `is_manual=1`.
- `nvl_balances` 593 (SXXK 582 · GC 11) · `sp_balances` 4.277 (SXXK 4.252 · GC 25)
- `norms` 79.139 (SXXK 79.117 · GC 22) · `declaration_lines` 21.342 (NK 6.008 + XK 15.334 đã gộp)
- 0 dòng tờ khai ngoài cửa sổ kỳ.
- Sau khi sửa dò loại hình theo sổ: **1.982 phát hiện**, risk 72.
  `C1.1=1 · C1.2=0 · C1.3=0 · C1.4=0 · C1.6=1 · C1.7=33 · C2.*=0 · C3.1=0 · C3.2=60 ·
  C3.3=4 · C4.1=901 · C4.3=982 · C5.1=0 · C6.1=0`
- Backup trước khi ghi: `/db-data/audit_hq.sqlite.bak-pre-dn005-20250401` (293 MB, tạo
  bằng SQLite backup API nên gồm cả WAL).
- Bản gốc 3 file bị vá tay nằm ở `/tmp/bak/` **trong container** (mất khi container dựng lại).

Nguồn file thô: `P:\Downloads\5. Takagi\5. Takagi` (WSL `/mnt/p/Downloads/5. Takagi/5. Takagi`).
**Không** copy lên prod — xem §4 mục 6.

## 2. Bản đồ cột đã ĐO (script tạm đã mất, chép lại ở đây)

Toàn bộ script staging/loader viết trong scratchpad và đã bị dọn. Bản đồ dưới đây là
thứ duy nhất còn lại; đo trực tiếp trên chính bộ file này.

**BCCT `BaoCaoHangChiTietMH` — 81 cột, tiêu đề dòng 0, `data_start=1`.** Đã encode
theo NHÃN trong `app/adapters/bcct.py` (chưa commit, §4 mục 1):

| trường | cột | trường | cột |
|---|---|---|---|
| Số TK | 1 | Mã HS | 58 |
| Ngày ĐK | 2 | Mã hàng | 59 |
| Mã loại hình | **4** | Tên hàng | 60 |
| Tên đối tác | 5 | Đơn vị tính | 61 |
| Số hóa đơn TM | 23 | Số lượng | 62 |
| Ng.Tệ hóa đơn | 28 | Đơn giá hóa đơn | 63 |
| Trị giá hóa đơn | 65 | Trị giá tính thuế | 66 |
| Tổng tiền thuế | **74** | Nước xuất xứ | 75 |

Hai bẫy: **c3 là `Mã HQ` (`03PL`), KHÔNG phải mã loại hình** — bố cục 8 DN pilot để mã
loại hình ở c3 nên bản đồ cứng đọc trôi mà sai toàn bộ; `Tổng tiền thuế` có ở CẢ c35
(cấp tờ khai) lẫn c74 (cấp dòng hàng) → phải lấy lần xuất hiện SAU.

**TT121 Mẫu 15 (`BCQT_NPL`)** — `data_start`: SXXK 9, GC 10:
`c0 STT · c1 mã · c2 tên · c3 ĐVT · c4 tồn đầu · c5 nhập · c6 tái xuất · c7 chuyển MĐSD ·
c8 xuất SX · c9 xuất khác · c10 tồn cuối`

**TT121 Mẫu 15a (`BCQT_SP`)** — `data_start`: SXXK 9, GC 10:
`c0 STT · c1 mã · c2 tên · c3 ĐVT · c4 tồn đầu · c5 nhập từ SX · c6 tái nhập khách trả lại ·
c7 chuyển MĐSD · c8 xuất khẩu · c9 xuất khác · c10 tồn cuối`
→ **`intake_qty` = c5 + c6**. Biểu chuẩn gộp một cột nhập, TT121 tách đôi; lấy một cột
là thiếu. Đã kiểm: cộng cả hai thì đẳng thức cân đối đúng khít 4.277/4.277 dòng.

**BCDM_TT39 (`BCTT39`, `data_start=11`)**:
`c1 mã SP · c2 tên SP · c3 ĐVT SP · c4 mã NPL · c5 tên NPL · c6 ĐVT NPL · c7 định mức`
Mã SP để trống = kế thừa dòng trên.

**KB03 (`BCDM SXXK 2025.xlsx`, sheet `KB03_1` + `KB03_2`, tiêu đề dòng 0)** — đây là bản
xuất ECUS ở mức LỆNH SẢN XUẤT, **không phải Mẫu 16**:
`c3 mã SP · c4 tên SP · c5 ĐVT SP · c6 mã NPL · c7 tên NPL · c8 ĐVT NPL · c9 lượng thực tế`
c9 là định mức trên MỘT đơn vị SP. 102.857 dòng → gộp theo `(mã SP, mã NPL)` còn
**79.117 cặp, 0 cặp nào có hai giá trị định mức khác nhau** → gộp là mất-không-gì.

**File CỐ Ý không dùng:**
- `BCQT SXXK T04.25-T03.26 05.06.2026. V01.xlsx` — đúng Mẫu 15/15a nhưng chèn thêm cột
  `Mã kế toán` làm lệch cột (sheet `152`: mã c1 nhưng tên đẩy sang c3; sheet `155`: mã
  hải quan ở c2) → `select_sheet` chấm 0. Trùng nội dung với TT121 (584≈582 và 4.252)
  nên bỏ, không phải mất dữ liệu.
- `Du lieu 2024.xlsx` — bố cục **thứ ba** (63 cột, `So_to_khai`/`Ngay_Dang_Ky`, tiêu đề
  dòng 0), là dữ liệu **2024**, CHƯA nạp.
- `Các mã chưa có định mức, chưa được truyền ĐM.xlsx` — danh sách tham chiếu, không phải biểu.

## 3. Hai lỗi thật đã tìm ra

**(a) `bcct.py` đọc bố cục lạ mà không báo lỗi.** Bản đồ cột cứng + `Số TK`/`Ngày ĐK`
tình cờ trùng vị trí → qua ngưỡng `select_sheet`, nuốt đủ 21.342 dòng, nhưng `Số lượng`
rỗng toàn bộ và `Mã loại hình` = `03PL` cho mọi dòng. Đã sửa sang đọc theo nhãn tiêu đề;
3 DN pilot ra kết quả **không đổi** (nhãn của họ trùng đúng vị trí `_COL` cũ).

**(b) Dò loại hình bầu một lần cho cả pháp nhân → sổ nhỏ luôn thua sổ lớn.** 17.756 dòng
E31/E62 áp đảo 250 dòng E82/E41 nên **cả hai sổ** đều bị coi là SXXK, cân đối sổ GC bị đem
so với tờ khai sổ SXXK → 43 phát hiện sai (C1.1 11 · C1.3 11 · C1.4 21). Gốc rễ không phải
thiếu mã trong một cái set mà là **cặp (tập mã, cột) bị gắn cứng**: mọi check đều lấy
`M15.import_qty` so với tập mã nhập. Sổ thuê gia công nước ngoài đảo chiều vật tư nên
phải đổi CẢ HAI vế. Ánh xạ đã đo, khớp tuyệt đối:

| | sổ SXXK | sổ GC (thuê gia công ở nước ngoài) |
|---|---|---|
| Mẫu 15 ↔ tờ khai | `import_qty` ↔ E31/E33 | `production_out_qty` ↔ **E82** |
| Mẫu 15a ↔ tờ khai | `export_qty` ↔ E62 | `intake_qty` ↔ **E41** |

11/11 mã NVL sổ GC có `production_out_qty` **bằng đúng** lượng E82. Đã sửa: thêm
`CompanyType.GIA_CONG_NN` + `Pairing` + `detect_book_types` (phiếu chỉ đếm tờ khai có mã
hàng thuộc sổ đó, vì `declaration_lines` không mang cột `book`). Cổng chặn
`mixed_book_pairings` trả `None` cho DN một sổ VÀ cho DN nhiều sổ **cùng** loại hình →
004 (EPE+GC đều DNCX) và toàn bộ DN hiện có giữ nguyên đường cũ. Đã xác minh chỉ-đọc trên
prod: chỉ DN_005 kích hoạt đường mới.

## 4. Việc còn lại

1. **Commit `app/adapters/bcct.py`** — +71 dòng, CHƯA commit, đang nằm nhầm trên nhánh
   `feat/adr23-ktstq-period-scope`. Nó độc lập với ADR #23 → tách nhánh riêng từ `main`.
2. **Merge `fix/per-book-company-type` (`0b9e3b2`) vào main + deploy.** Prod đang chạy nó
   **chỉ dưới dạng vá tay trong container**; deploy CI kế tiếp ghi đè và 43 phát hiện sai
   quay lại. Nhánh đã có commit đầy đủ, ruff sạch, full test 0 failed (một test bắt được
   loại hình mới thiếu nhãn UI → đã thêm "Thuê gia công ở nước ngoài").
3. **Viết adapter KB03 → m16 thật.** Đã chốt làm nhưng mới chỉ hiện thực trong script
   staging tạm (đã mất). 79.117 dòng định mức đang nằm trong DB prod, nhưng **hệ thống
   vẫn chưa đọc được file `BCDM SXXK 2025.xlsx`**. Bản đồ cột ở §2.
4. **C4.1 = 901 / C4.3 = 982 phần lớn là nhiễu — đừng trình như vi phạm.** 896/901 phát
   hiện có mã NPL không nằm trong Mẫu 15, vì định mức KB03 liệt kê MỌI NPL kể cả mua
   trong nước (`NYAA0260AABV`, `100070AVQ01`…) còn Mẫu 15 chỉ có NPL **nhập khẩu**
   (890/1.396 mã lệch). Cần lọc theo nguồn NPL hoặc tách severity trước khi dùng.
5. **Nạp 2024** từ `Du lieu 2024.xlsx` — cần hỗ trợ bố cục BCCT thứ ba (§2).
6. **Trang tài liệu đang trống** vì cố ý không copy file Excel lên prod: `bcct.py` bản
   prod vẫn đọc sai bố cục này, có file trên đĩa thì ai bấm nạp lại từ trang tài liệu sẽ
   **ghi đè dữ liệu tốt bằng rác**. Chỉ copy file lên sau khi mục 1 đã deploy.
7. **`denominators.py` chưa đụng** — vẫn dùng loại hình toàn DN. Chỉ ảnh hưởng mẫu số khi
   tính điểm, không quyết định phát hiện nào nổ. Để nguyên cho hẹp phạm vi vá tay.
8. **C1.4 = 0 cho sổ SXXK** (4.252 SP đối chiếu E62) — số 0 này có TỪ TRƯỚC khi sửa, chưa
   xác minh là sạch thật hay "sạch giả". Kiểm trước khi đem ra demo.
9. **Đổi tên/ẩn danh nếu cần** — hiện chỉ tên là giả, MST + địa chỉ vẫn thật.
