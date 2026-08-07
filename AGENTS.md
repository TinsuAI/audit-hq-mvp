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
- **Phiên DB:** module mới KHÔNG được `from app.database import SessionLocal` ở mức module. `from ... import` chụp đối tượng ngay lúc import, nên vá `app.database.SessionLocal` không đổi được bản sao đó và test sẽ ghi thẳng vào DB của máy dev. Dùng một trong hai: nhận `Session` qua tham số (route thì `Depends(get_db)`), hoặc `import app.database as dbmod` rồi gọi `dbmod.SessionLocal()` để phân giải lúc chạy. Bốn module còn giữ bản sao cũ (`app/main.py`, `app/ai/config.py`, `app/pipeline/ingest.py`, `app/pipeline/run_checks.py`) là nợ kỹ thuật, không phải mẫu để chép.
- **Test đi qua route hoặc hàng đợi:** dùng fixture chung `app_db` (`tests/conftest.py`), KHÔNG tự dựng engine + tự vá `app.database`. `app_db` vá engine, phiên ở `app.database`, và bản sao phiên đã import vào mọi module `app.*`; kèm sẵn schema, admin `admin/admin`, và `settings.raw_data_path` trỏ vào `tmp_path`. `tests/test_db_fixture_isolation.py` giữ ràng buộc này.

## Skills project-scoped

- `/tdd` — viết test trước cho check. Mỗi rule có test fixture nhỏ (3-5 dòng Excel mock).
- `/rev` — review trước khi merge mỗi nhóm check.

## Agent skills

### Issue tracker

GitHub Issues của `TinsuAI/audit-hq-mvp`, thao tác qua `gh`. PR KHÔNG phải kênh nhận yêu cầu — `/triage` chỉ đọc issue. Xem `docs/agents/issue-tracker.md`.

### Triage labels

Dùng đúng 5 nhãn chuẩn: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Xem `docs/agents/triage-labels.md`.

### Domain docs

Single-context, nhưng KHÔNG dùng `CONTEXT.md` + `docs/adr/`. Glossary là `.ai/GLOSSARY.md`, ADR là `.ai/DECISIONS.md` (một file, đánh số toàn cục, tham chiếu dạng "ADR #N"). Xem `docs/agents/domain.md`.

## Không làm

- Không viết check ngoài 16 MVP trước tuần 6.
- Không refactor adapter sang ORM khác giữa chừng.
- Không commit `.sqlite`, file Excel thực, hay output anonymize.
- Không sửa catalog 50 check ở đây — sửa trong repo đề án trước.
