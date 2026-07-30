# Trạng thái đã soát / chưa soát cho finding — thiết kế

Phạm vi tài liệu này: thiết kế, không cài đặt. Không sửa file sản phẩm, không viết migration,
không đụng git. Nguồn vấn đề: `.ai/STATUS.md` khối 2026-07-29, mục Next (3) — finding không có
trạng thái đã-soát/chưa-soát, cán bộ quay lại màn thì thấy lại toàn bộ tập hợp finding của
(DN, năm), không có dấu vết đã xem dòng nào. Số liệu thật để tham chiếu quy mô: `PILOT_006/2025`
có 10.996 finding (đo trực tiếp trên `audit_hq.sqlite`), ba kiểm tra C1.6 (5.785) · C1.7 (2.436) ·
C4.3 (1.772) chiếm 91%.

## 1. Câu hỏi quyết định: có khoá nào ổn định qua một lần chạy lại kiểm tra không

**Có.** Khoá tự nhiên `(company_id, period_year, check_code, subject_key, book)` ổn định qua
re-run, với một ngoại lệ đã đo được và nêu rõ ở dưới. `finding.id` thì KHÔNG ổn định — bằng chứng:

- `app/pipeline/run_checks.py:78-85` xoá cứng (`delete(Finding)`) mọi finding của
  `(company_id, period_year)` khớp `check_code` sắp chạy lại, TRƯỚC khi chèn finding mới. Dòng
  96-104 xoá vô điều kiện toàn bộ `COMBO_%` mỗi lần chạy. Bảng không có cột nào giữ id cũ — mỗi
  finding mới nhận `id` autoincrement mới.
- Bằng chứng thực nghiệm đã có sẵn trong `.ai/STATUS.md:125-141`: chạy lại kiểm tra 004 trên prod
  (do sửa lỗi multi-unit) làm 74 → 65 finding, "9 dòng bị xoá, 0 dòng thêm mới" — xác nhận cơ chế
  xoá-rồi-tạo-lại là hành vi thật, không phải suy luận từ đọc code.
- `subject_key` thì ngược lại: nó là mã nghiệp vụ đọc trực tiếp từ Tầng 1 (`material_code`,
  `product_code`...), không phải giá trị sinh ra bởi hệ thống. Ví dụ `check_c1_6`
  (`app/checks/c1_quantity.py:429-473`) và `check_c1_7` (dòng 476-522) gán
  `subject_key=r.material_code` từ `NvlBalance`; `check_c4_3` (`app/checks/c4_norm.py:190-196`)
  cũng vậy. Với dữ liệu Tầng 1 không đổi, hàm check là hàm thuần (chỉ SELECT, không random, sort
  tường minh trước khi lặp) nên chạy lại cho đúng cùng một tập `subject_key`.
- Đã kiểm tra trùng lặp thật trên `audit_hq.sqlite`: nhóm theo
  `(company_id, period_year, check_code, subject_key, book)` — **0 nhóm trùng cho C1.6, C1.7, C4.3**
  (ba kiểm tra chiếm 91% khối lượng). Khoá này là khoá 1-1 với finding ở ba kiểm tra đó, khớp đúng
  quan sát ở `.ai/sessions/2026-07-29-dashboard-ux-prototype.md` dòng "mọi finding có subject_key
  DUY NHẤT".

**Ngoại lệ đã đo, nêu rõ để không giấu:** `PILOT_004` (company_id=9) có 4 cặp finding trùng
`(check_code, subject_key)` ở C1.1 và C1.3 (vd `subject_key='6064592-08B'`, `check_code='C1.1'`,
2 dòng) — đây là vật tư ghi nhận ở HAI đơn vị tính khác nhau (MTR và ROLL) trong cùng kỳ, mỗi đơn
vị cho ra một finding riêng (`app/checks/c1_quantity.py:180-238`, hàm `_unit_targets`). `book` không
tách được hai dòng này (cả hai cùng `book='EPE'`) — thứ tách được là `details.unit`, một trường
JSON, không phải cột lọc được rẻ. Ảnh hưởng: 4 mã / 8 finding trên tổng ~15.000 (0,05%), chỉ ở
C1.1/C1.3/C1.4 (không phải 3 kiểm tra chiếm 91%). Quyết định phạm vi: KHÔNG đưa `unit` vào khoá ở
MVP — một dấu "đã soát" trên khoá 5 cột sẽ áp cho cả hai dòng đơn-vị-khác-nhau của cùng vật tư, đây
là hành vi có thể chấp nhận (cán bộ nghĩ theo vật tư, không theo lát đơn vị) và được ghi lại ở đây
để không phải bất ngờ sau này.

**Phát hiện phụ, không thuộc yêu cầu này nhưng là bằng chứng trực tiếp cho quyết định thiết kế ở
mục 2:** cột `status`/`notes` hiện có trên `Finding` (`app/models/finding.py:31-32`,
`app/routes/companies.py:2406-2431`) CŨNG bị xoá bởi đúng cơ chế trên — không có `Finding()` nào
trong `app/checks/*.py` truyền `status=`, nên mỗi lần chạy lại, finding mới luôn nhận default
`"new"`, xoá sạch mọi phân loại "Xác nhận"/"Loại trừ"/"Đã ghi chú" + ghi chú tay mà cán bộ đã nhập
trước đó. Đây là lỗi đang tồn tại, chưa có ticket, không thuộc phạm vi bản thiết kế này — nêu ra vì
nó chứng minh bằng thực tế (không chỉ bằng suy luận) rằng một cột nằm trên chính dòng `Finding` là
lựa chọn sai cho bất cứ thứ gì cần sống qua một lần chạy lại.

## 2. Trạng thái cần có

**Khuyến nghị: nhị phân — đã soát / chưa soát, không thêm tầng "đã xử lý"/"bỏ qua"/"cần theo dõi".**

Vấn đề cán bộ nêu (STATUS.md) là theo dõi ĐÃ XEM hay CHƯA, không phải phân loại kết luận. Phân loại
kết luận đã có sẵn ở cột `status`: `new` (mới) · `confirmed` (xác nhận vấn đề thật) · `rejected`
(loại trừ, tác động thẳng vào điểm rủi ro qua `app/checks/scoring.py:76,100,166`) · `noted` (đã ghi
chú), có UI ở `app/routes/companies.py:92-98` và form tại `app/templates/finding_detail.html:118-134`.
"Đã xử lý" trùng nghĩa với `confirmed`/`rejected`; "cần theo dõi" trùng nghĩa với `new` + ghi chú;
"bỏ qua" trùng nghĩa với `rejected`. Dựng thêm một trục ba giá trị song song với trục bốn giá trị
đã có, cả hai đều trả lời câu "dòng này tới đâu rồi", sẽ tạo hai từ vựng cạnh tranh mà không có bằng
chứng nào trong code hay STATUS.md cho thấy cán bộ cần phân biệt chúng. Không có yêu cầu nào từ
nghiệp vụ đòi hỏi trục thứ ba — chỉ có yêu cầu "biết đã xem chưa", đúng bằng một cờ nhị phân.

Thiết kế: sự TỒN TẠI của một dòng trong bảng mới = đã soát; không tồn tại = chưa soát. Không cần
cột `review_state` kiểu chuỗi ở MVP. Nếu sau này thật sự cần nhiều trạng thái hơn (ví dụ tách "đã
soát, chờ theo dõi tiếp" khỏi "đã soát, xong"), điểm mở rộng là thêm một cột enum vào ĐÚNG bảng này
— khoá tự nhiên không đổi, không phải thiết kế lại.

**Ai đặt, khi nào:** cán bộ (role `officer` hoặc `admin`, giống quyền hiện có ở route status —
`Depends(require_user)`, không giới hạn thêm) bấm nút trên dòng finding (màn danh sách
`company_detail.html` hoặc màn chi tiết `finding_detail.html`) → ghi `reviewed_by` (từ
`SessionUser.name` tra ra `User.id`, đúng pattern `user_row.id` đã dùng ở
`app/routes/companies.py:1439,1452,1517,1580`), `reviewed_at` (thời điểm ghi), `note` (tuỳ chọn,
ngắn). KHÔNG tự động đặt bởi hệ thống (chạy kiểm tra xong không tự đánh dấu đã soát — làm vậy thì
mất hết ý nghĩa của trạng thái này).

**Khi finding biến mất ở lần chạy lại (khoá không còn khớp dòng finding nào):** giữ nguyên dòng
trong bảng đánh dấu. KHÔNG xoá theo. Lý do: dòng đánh dấu là bằng chứng "cán bộ X đã xem việc này
lúc Y" — hữu ích để giải trình sau này (ví dụ đúng ca 004: một lỗi tính sai bị sửa làm 9 finding
biến mất; nếu cán bộ đã soát một trong 9 dòng đó trước khi sửa, bằng chứng đã-soát vẫn nên còn để
biết cán bộ không bỏ sót, chỉ là dữ liệu đã đổi). Dòng mồ côi không hiện ở đâu trong màn hiện tại
(màn chỉ JOIN từ `findings` sang bảng đánh dấu, không truy vấn chiều ngược lại) — không cần dọn dẹp
ở MVP.

**Khi finding tái xuất (cùng khoá tự nhiên xuất hiện lại ở lần chạy sau):** tự động nối lại — cán bộ
thấy ngay "đã soát lúc Y" dù `finding.id` là dòng mới. Đây là hành vi ĐÚNG khi dữ liệu Tầng 1 không
đổi bản chất. Rủi ro đã biết, KHÔNG xử lý ở MVP: nếu số liệu bên trong finding đổi đáng kể (vd
`diff_pct` từ -12% nhảy lên -60% dù cùng `subject_key`/`check_code`), dấu "đã soát" cũ vẫn hiện ra
như thể không có gì thay đổi — cán bộ có thể bỏ sót một mức độ nghiêm trọng mới mà không biết đã bị
che bởi dấu cũ. Ghi nhận ở đây, xử lý ở vé T5 (mục 4), không đưa vào phạm vi cài đặt đầu tiên.

**Quan hệ với `status`:** bảng đánh dấu KHÔNG thay thế, KHÔNG mở rộng `status`. Hai trục độc lập —
"đã xem chưa" và "kết luận là gì". Một finding có thể đã soát mà vẫn `status='new'` (xem rồi, chưa
kết luận). Lý do dùng bảng riêng thay vì thêm cột lên `Finding`: đã chứng minh ở mục 1 rằng bất cứ
cột nào nằm trên `Finding` bị xoá theo dòng mỗi lần chạy lại — thêm `reviewed_at` lên `Finding` sẽ
tái tạo đúng lỗi mà `status` đang mắc phải hôm nay.

## 3. Hình dạng cài đặt cụ thể

### Bảng mới `finding_reviews`

```python
# app/models/finding_review.py
class FindingReview(Base):
    __tablename__ = "finding_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    check_code: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    book: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "company_id", "period_year", "check_code", "subject_key", "book",
            name="uq_finding_review",
        ),
    )
```

`check_code` dùng `String(32)` (khớp `CheckRun.check_code`, không phải `String(16)` của `Finding` —
combo và check động có thể dài hơn 16 ký tự, `COMBO_HS_GAMING` đã dài 15). `subject_key`/`book`
khớp đúng độ dài cột nguồn trên `Finding`.

**Lưu ý SQLite về NULL trong UNIQUE constraint:** hai dòng cùng
`(company_id, period_year, check_code, subject_key, book=NULL)` KHÔNG bị chặn trùng bởi constraint
— chuẩn SQL coi NULL luôn khác NULL. Đa số DN trong hệ thống là một sổ (`book` luôn NULL), nên
không dựa vào UNIQUE constraint để chống trùng khi ghi — ghi theo kiểu tra-trước-rồi-ghi (SELECT
theo khoá đủ 5 cột, có nếu không tạo), đúng pattern `existing_runs` đã dùng ở
`app/pipeline/run_checks.py:200-224` cho `CheckRun`. Constraint vẫn giữ như một lớp chặn phụ cho
trường hợp `book` có giá trị.

**Index cần thêm: không cần thêm gì ngoài UNIQUE constraint.** UNIQUE constraint tự tạo index phủ
đúng thứ tự `(company_id, period_year, check_code, subject_key, book)` — tiền tố
`(company_id, period_year, check_code)` của chỉ mục này đã đủ cho truy vấn gom nhóm ở màn danh sách
(mục dưới). Không cần chỉ mục riêng.

### Migration outline (alembic)

Head hiện tại xác nhận qua `python -m alembic heads`: **`c5d6e7f8a9b0`**.

```python
# migrations/versions/<new_id>_finding_reviews.py
revision = "<new_id>"
down_revision = "c5d6e7f8a9b0"

def upgrade() -> None:
    op.create_table(
        "finding_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("check_code", sa.String(length=32), nullable=False),
        sa.Column("subject_key", sa.String(length=128), nullable=False),
        sa.Column("book", sa.String(length=32), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "period_year", "check_code", "subject_key", "book",
            name="uq_finding_review",
        ),
    )
    with op.batch_alter_table("finding_reviews", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_finding_reviews_reviewed_by"), ["reviewed_by"], unique=False,
        )

def downgrade() -> None:
    with op.batch_alter_table("finding_reviews", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_finding_reviews_reviewed_by"))
    op.drop_table("finding_reviews")
```

Đăng ký model trong `app/models/__init__.py` (thêm `FindingReview` vào import + `__all__`, theo
đúng thứ tự alphabet đã dùng).

### Thay đổi câu truy vấn ở màn danh sách (`app/routes/companies.py`, hàm `company_detail`)

Câu đếm theo nhóm hiện tại (dòng 1704-1712) chỉ nhóm theo `check_code, severity`. Thêm chiều
đã-soát bằng LEFT JOIN, so `book` bằng `IS` (null-safe trong SQLite) chứ không phải `==`:

```python
is_reviewed = FindingReview.id.is_not(None)
rows = db.execute(
    select(Finding.check_code, Finding.severity, is_reviewed, func.count())
    .outerjoin(
        FindingReview,
        (FindingReview.company_id == Finding.company_id)
        & (FindingReview.period_year == Finding.period_year)
        & (FindingReview.check_code == Finding.check_code)
        & (FindingReview.subject_key == Finding.subject_key)
        & (FindingReview.book.is_(Finding.book)),
    )
    .where(
        Finding.company_id == company.id,
        Finding.period_year == selected_year,
        *_book_clause(),
    )
    .group_by(Finding.check_code, Finding.severity, is_reviewed)
).all()
```

Cộng dồn thêm `reviewed_counts[ccode]` song song `counts[ccode][sev]` hiện có, và tổng
`total_reviewed` song song `total_findings` (dòng 1731). Hàm `_rows()` (dòng 1763-1775) thêm tham số
lọc `unreviewed_only: bool`, cùng kiểu `outerjoin` + `.where(FindingReview.id.is_(None))` khi bật —
phục vụ query param mới `?reviewed=chua` (đối xứng với `?book=` đã có). Trang chi tiết 1 nhóm/1
trang (`_rows` gọi ở dòng 1782, `_PAGE_SIZE=100`) tải kèm `FindingReview` cho đúng các
`subject_key` đang hiển thị (một câu `WHERE subject_key IN (...)` phạm vi trang, không phải toàn
bộ 10.996 dòng) để hiện "đã soát lúc..." trên từng dòng.

### UI affordance (tiếng Việt)

- **Trên mỗi dòng finding** (`company_detail.html:431-444`, cạnh `status-pill` hiện có): nút
  "Đánh dấu đã soát" — bấm xong đổi thành nhãn "Đã soát lúc {giờ} · {tên cán bộ}" kèm nút "Bỏ đánh
  dấu". Không gộp vào `<select name="status">` hiện có — hai trục độc lập, gộp sẽ khiến cán bộ hiểu
  nhầm "đã soát" là một lựa chọn kết luận.
- **Thanh tiến độ theo nhóm kiểm tra** (đầu mỗi bảng, cạnh tiêu đề nhóm hiện ở dòng ~421): "Đã soát
  12/5.785".
- **Thanh tổng ở đầu trang**: "Đã soát 1.204/10.996 (11%)".
- **Bộ lọc "Chỉ hiện chưa soát"** — toggle cạnh bộ lọc `?book=` đã có (multi-book), query param
  `?reviewed=chua`. Mặc định TẮT (hiện tất cả) ở lần đầu ghé màn trong phiên, để không giấu dữ liệu
  ngoài ý muốn cán bộ mới.
- **Màn chi tiết** (`finding_detail.html:118-134`): cùng nút, đặt phía trên form trạng thái hiện có,
  không chung form.

## 4. Vé tracer-bullet

- **T1 — Migration + model `finding_reviews`.** Không phụ thuộc vé nào. Chặn T2, T3.
- **T2 — Route ghi.** `POST /findings/{finding_id}/review` (đánh dấu) và
  `POST /findings/{finding_id}/review/undo` (bỏ đánh dấu). Đọc khoá tự nhiên từ chính dòng
  `Finding` đang sống tại thời điểm bấm (không cần cán bộ nhập tay 5 cột khoá), xác thực quyền
  bằng `can_access_company_id` giống route status hiện có (`app/routes/companies.py:2406-2431`).
  Ghi theo kiểu tra-trước-rồi-ghi (mục 3). Phụ thuộc T1.
- **T3 — Đổi câu truy vấn màn danh sách.** LEFT JOIN + đếm đã-soát ở `company_detail()`, thêm tham
  số lọc ở `_rows()`, thêm `?reviewed=chua`. Phụ thuộc T1. Độc lập với T2 (có thể lên trước, chỉ
  đọc — hiện tiến độ 0/10.996 trước khi có nút ghi cũng không sai).
- **T4 — UI.** Nút đánh dấu + thanh tiến độ + toggle lọc, ở cả `company_detail.html` và
  `finding_detail.html`. Phụ thuộc T2 và T3.
- **T5 — không làm ngay, chỉ gắn cờ để không quên:**
  (a) dấu vân tay nội dung (hash `severity` + các trường số trong `details`) để phát hiện một
  finding tái xuất nhưng đã đổi bản chất, tránh dấu "đã soát" cũ che một mức độ nghiêm trọng mới —
  nêu ở mục 2;
  (b) đưa `unit` vào khoá cho 4 cặp finding trùng ở C1.1/C1.3 nếu sau này phát sinh yêu cầu tách
  riêng theo đơn vị — nêu ở mục 1;
  (c) áp dụng lại đúng mẫu bảng khoá-tự-nhiên này cho `status`/`notes` hiện có trên `Finding`, vì
  chúng đang mắc cùng lỗi mất dữ liệu qua re-run đã chứng minh ở mục 1 — đây là một quyết định
  riêng, cần bàn riêng vì `status` còn tác động trực tiếp vào điểm rủi ro
  (`app/checks/scoring.py:76,100,166`) và kích hoạt `recompute_company_year`
  (`app/routes/companies.py:2429-2430`), không đơn thuần là đổi chỗ lưu.
