# Cẩm nang hướng dẫn sử dụng — trang HTML tự chứa + ảnh chú số

Thay tài liệu hướng dẫn cũ (`docs/huong-dan-su-dung.md`, bản 2026-06-14 commit `00959b1`,
không ảnh) bằng **cẩm nang HTML tự chứa**: mục lục bên trái, ô tìm kiếm không dấu, 37 thẻ
hướng dẫn theo 8 mục, mỗi thao tác kèm **ảnh chụp thật có khung đỏ và số thứ tự** khớp
đúng số của từng bước bên cạnh. Định dạng dựng theo mẫu cẩm nang Clavis của Trọng Tín.

## Nằm ở đâu

```
app/static/docs/huong-dan/
├── index.html          ← cẩm nang (CSS + JS nội tuyến, không phụ thuộc mạng)
└── *.png               ← 35 ảnh, tên trùng với id thẻ hướng dẫn
```

Thư mục này **copy sang host tĩnh khác là chạy được nguyên vẹn** (ảnh tham chiếu tương đối).
Trong ứng dụng: thẻ "Cẩm nang sử dụng Audit-HQ" ở `/tai-lieu` trỏ thẳng vào
`/static/docs/huong-dan/index.html`; slug cũ `/tai-lieu/huong-dan-su-dung` trả **307** về
đó để link đã phát ra ngoài vẫn chạy (`app/routes/docs.py`).

**Ảnh KHÔNG theo convention `.ai/features/<slug>/screenshots/`** vì đây là ảnh **sản phẩm**
của tài liệu giao cho khách, phải nằm dưới mount `/static` mới phục vụ được. Ảnh chứng E2E
của từng vé vẫn theo convention cũ.

## Chú số trên ảnh

`annotate(page, [(selector, số, {...})])` trong `scripts/guide_screenshots.py` chèn một lớp
phủ vào DOM **trước khi chụp**: khung đỏ `#e11d48` quanh phần tử + huy hiệu tròn mang số.
Selector dùng cú pháp Playwright (kể cả `:has-text()`) — phần tử được gắn thuộc tính tạm rồi
mới vẽ. Selector không khớp, hoặc phần tử kích thước 0 (nằm trong `<details>` đang đóng),
thì **script dừng** — không để lọt ảnh thiếu chú số.

Số trong ảnh phải khớp `<ol>` bước của thẻ hướng dẫn tương ứng trong `index.html`. Sửa một
bên thì sửa cả hai.

## Chụp lại

Chạy trên **bản sao** DB dev + server riêng — KHÔNG đụng `audit_hq.sqlite` live, KHÔNG đụng
cổng 8200 của user, KHÔNG ghi vào `data/`.

```bash
SCRATCH=<thư mục tạm>

# 1. Sao DB dev (WAL-safe) rồi nâng lên head
.venv/bin/python - <<'PY'
import sqlite3
src = sqlite3.connect("file:audit_hq.sqlite?mode=ro", uri=True)
dst = sqlite3.connect("<SCRATCH>/guide.sqlite")
src.backup(dst)
PY
DATABASE_URL="sqlite:///$SCRATCH/guide.sqlite" .venv/bin/alembic upgrade head

# 2. Hai tài khoản chụp ảnh trong bản sao
DATABASE_URL="sqlite:///$SCRATCH/guide.sqlite" PYTHONPATH=. .venv/bin/python - <<'PY'
from app.auth_users import create_user, get_user_by_username
from app.database import SessionLocal
with SessionLocal() as db:
    for name, role in (("hdsd_admin", "admin"), ("hdsd_canbo", "officer")):
        if not get_user_by_username(db, name):
            create_user(db, name, "hdsd12345", role)
    db.commit()          # create_user chỉ flush — thiếu commit thì login 401
PY

# 3. Server throwaway, kill theo PID (KHÔNG pkill -f uvicorn)
setsid env DATABASE_URL="sqlite:///$SCRATCH/guide.sqlite" RAW_DATA_PATH="$SCRATCH/data" \
    .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8342 --no-access-log \
    > "$SCRATCH/guide-server.log" 2>&1 < /dev/null &
echo $! > "$SCRATCH/guide.pid"

# 4. Chụp
G_BASE=http://127.0.0.1:8342 DATABASE_URL="sqlite:///$SCRATCH/guide.sqlite" \
    RAW_DATA_PATH="$SCRATCH/data" PYTHONPATH=. \
    .venv/bin/python scripts/guide_screenshots.py

kill "$(cat "$SCRATCH/guide.pid")"
```

`G_STAGES=bc` chạy lại một phần (a = nhập liệu, b = đọc kết quả, c = trợ lý + quản trị,
d = góc nhìn cán bộ).

## Kịch bản chụp

| Phần | Dữ liệu | Ảnh |
|---|---|---|
| A. Quy trình nhập liệu | DN mới tạo qua giao diện, file thật từ `demo-data/Công ty TNHH May Mặc Hoa Sen (Demo)/2024` | 00–11 |
| B. Đọc kết quả | dữ liệu pilot trong bản sao (`PILOT_006` nhiều phát hiện, `PILOT_004` hai sổ EPE/GC) | 12–22b |
| C. Trợ lý + quản trị | như trên, thêm một lượt hỏi đáp thật | 23–32 |
| D. Góc nhìn cán bộ | `hdsd_canbo` được phân công 2 DN | 33 |

`reset_demo_company()` xoá DN của lượt trước nên chạy lại cho ra cùng kết quả.

## Hai ảnh gọi LLM thật

`22b-tong-quan-ai.png` và `23-tro-ly-ai.png` là output **thật** của mô hình — tổng quan sinh
qua đúng đường job, hỏi đáp gửi qua `/api/chat/stream`. Chi phí một lượt khoảng 0,002 USD.
Lần chạy sau **dùng lại bản ghi đã có trong DB** nên không tốn thêm lời gọi; muốn sinh mới
thì xoá dòng `check_overviews` / `ai_conversations` trong bản sao trước khi chạy.

## Che thông tin nhạy cảm

Ảnh nằm dưới `/static`, phục vụ **không cần đăng nhập**. Trước khi chụp `/admin/ai`, script
ghi đè chuỗi mã API đã che của ứng dụng (`sk-o••••b629` — vẫn lộ 4 ký tự cuối) thành
`sk-o••••••••`. Thêm màn hình nào có bí mật thì phải che tương tự.

## Lỗi thật bắt được khi chụp

**Sinh tổng quan AI hỏng im lặng khi phản hồi chạm trần `max_tokens`.** Lượt sinh cho
`PILOT_004/2025 C1.2` trả JSON **bị cắt giữa chừng** ở đúng 1024 token out (giá trị
`max_tokens` đang cấu hình). `parse_sections` bắt `JSONDecodeError` → trả `None` →
`sections_json` để NULL, nhưng `status` vẫn ghi `done` và `ov.content` vẫn giữ chuỗi JSON
thô. Giao diện xuống cấp về nhánh "JSON hỏng → in đoạn văn thô", tức **in nguyên khối JSON
cho cán bộ đọc**, không có nhãn nào báo hỏng.

- `finish_reason` của phản hồi (`length` khi bị cắt) đang **không được đọc**.
- Cùng họ với hai lỗi đã ghi ở STATUS (`request_timeout_s` không áp trên đường sinh tổng
  quan; luật cũ-mới bỏ sót dòng lỗi thời định dạng): trạng thái `done` không phản ánh việc
  nội dung không dùng được.
- Để chụp được ảnh, bản sao đã nâng `max_tokens` lên 3000 — **chỉ trong bản sao**, cấu hình
  live chưa đụng. Đây là cách né, không phải bản vá.

## Ghi chú môi trường

`audit_hq.sqlite` local ghi `alembic_version = d0e1f2a3b4c5` nhưng **đã có sẵn bảng
`ai_usage`** → `alembic upgrade head` dừng ở `f2a3b4c5d6e7` với lỗi *table ai_usage already
exists*. Trên bản sao xử lý bằng cách xoá bảng rỗng đó rồi nâng tiếp (`ai_usage` local có 0
dòng). **DB live chưa được sửa** — ai nâng cấp DB dev sẽ gặp lại. Cùng loại lệch với
`local-db-schema-drift`: số revision không phản ánh schema thật.
