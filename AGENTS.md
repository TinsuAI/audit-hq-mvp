# Audit-HQ MVP — AI Agent Rules

> Repo này là **implementation** cho đề án Audit-HQ. Catalog 50 kiểm tra ở repo đề án [`audit-hq`](../audit-hq/) — đừng thay đổi mô tả check ở đây trước khi update đề án.

## Mục đích

10 tuần xây demo 16 kiểm tra MVP (§7 đề án) trên dữ liệu thực 6 DN đã anonymize. Output cuối: demo 5 phút (§6.3 đề án) chạy trên `audit-hq-demo.tinsu.ai`.

## Quy trình

1. Đọc `.ai/STATUS.md` + `.ai/DECISIONS.md` + 2-3 session gần nhất.
2. Đọc đề án `../audit-hq/de-an-audit-hq.md` mục §4-7 khi cần ngữ nghĩa nghiệp vụ.
3. Implement theo lộ trình tuần (§7 đề án + `../audit-hq/.ai/sessions/2026-05-21-demo-plan.md`).
4. Mỗi rule: 1 file `app/checks/cN_*.py` + 1 file test `tests/test_checks/test_cN_*.py`.
5. Update `.ai/STATUS.md` sau mỗi session.

## Rules

- **Stack:** Python 3.12+, FastAPI, SQLAlchemy + Alembic, SQLite (dev + demo), pandas + openpyxl/xlrd, Jinja2. KHÔNG thêm framework lớn (Django, Celery) nếu không cần.
- **Tuần 1-2:** chỉ adapter + DB. KHÔNG viết checks chưa tới lượt.
- **Tuần 3-6:** mỗi tuần đúng nhóm check theo lộ trình. Không vượt scope.
- **Dữ liệu thực** trong `data/` (gitignored, symlink). KHÔNG commit. KHÔNG log raw vào console / file log.
- **Anonymize** chỉ chạy ở tuần 7 (`scripts/anonymize.py`). Trước tuần 7 dev trên dữ liệu thực.
- **Truy nguồn:** mọi phát hiện phải có FK về dòng dữ liệu Tầng 1 (§5.1 đề án) — không phát hiện nào được "hộp đen".
- **AI calls** (chuẩn hoá tên hàng §5.3): cache hard, fallback heuristics. KHÔNG gọi LLM trong rule logic.
- **Ngôn ngữ UI:** tiếng Việt full accents, tone formal — same đề án.

## Skills project-scoped

- `/tdd` — viết test trước cho check. Mỗi rule có test fixture nhỏ (3-5 dòng Excel mock).
- `/rev` — review trước khi merge mỗi nhóm check.

## Không làm

- Không viết check ngoài 16 MVP trước tuần 6.
- Không refactor adapter sang ORM khác giữa chừng.
- Không commit `.sqlite`, file Excel thực, hay output anonymize.
- Không sửa catalog 50 check ở đây — sửa trong repo đề án trước.
