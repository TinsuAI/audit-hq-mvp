import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import login_guard
from app.ai.config import seed_defaults as seed_ai_defaults
from app.ai.retention import run_retention_loop
from app.auth import (
    SESSION_COOKIE_NAME,
    SessionUser,
    login_with_credentials,
    make_session_cookie,
    require_user,
)
from app.auth_users import get_user_by_username, seed_default_admin, set_password
from app.database import SessionLocal, get_db
from app.errors import register_error_handlers, strip_empty_query_params
from app.jobs import register_handler
from app.jobs.handlers import ingest_handler, run_batch_handler, run_checks_handler
from app.jobs.worker import JobWorker, recover_zombie_jobs
from app.models.job import AI_JOB_KINDS, JobKind
from app.routes.admin import router as admin_router
from app.routes.admin_ai import router as admin_ai_router
from app.routes.admin_audit import router as admin_audit_router
from app.routes.admin_checks import router as admin_checks_router
from app.routes.admin_display import router as admin_display_router
from app.routes.admin_risk_tiers import router as admin_risk_tiers_router
from app.routes.admin_users import router as admin_users_router
from app.routes.ai import router as ai_router
from app.routes.catalog import router as catalog_router
from app.routes.chat_page import router as chat_page_router
from app.routes.companies import router as companies_router
from app.routes.docs import router as docs_router
from app.routes.jobs import router as jobs_router
from app.settings import settings
from app.version import BUILD_SHA, BUILD_TIME, VERSION, version_string

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version"] = VERSION
templates.env.globals["app_version_string"] = version_string()
templates.env.globals["app_build_sha"] = BUILD_SHA
templates.env.globals["app_build_time"] = BUILD_TIME


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed AI settings từ env vars khi bảng trống. Idempotent.
    try:
        inserted = seed_ai_defaults()
        if inserted:
            log.info("Seeded %d default AI settings", inserted)
    except Exception:
        log.exception("AI seed_defaults failed (continuing without AI)")

    # Seed admin user đầu tiên từ env nếu bảng users trống.
    try:
        with SessionLocal() as db:
            seeded = seed_default_admin(db, settings.auth_user, settings.auth_password)
            if seeded:
                log.info("Seeded default admin user: %s", seeded.username)
        # Cảnh báo to nếu admin còn dùng mật khẩu mặc định — pilot dữ liệu thật KHÔNG nên.
        if settings.auth_password in ("admin", "", None):
            log.warning(
                "AUTH_PASSWORD đang là mặc định/không an toàn — đổi ngay qua /change-password "
                "hoặc đặt env AUTH_PASSWORD trước khi chạy thí điểm thật."
            )
    except Exception:
        log.exception("seed_default_admin failed (login sẽ không hoạt động)")

    # Retention cleanup loop — non-critical, failure logged not raised.
    retention_task = asyncio.create_task(run_retention_loop())

    # Async job runner: recover zombies + start worker thread.
    try:
        register_handler(JobKind.RUN_CHECKS, run_checks_handler)
    except ValueError:
        pass  # idempotent: tests có thể đã register
    try:
        register_handler(JobKind.BATCH_RUN, run_batch_handler)
    except ValueError:
        pass
    try:
        register_handler(JobKind.INGEST, ingest_handler)
    except ValueError:
        pass
    try:
        from app.ai.overview import run_overview_batch_job, run_overview_job

        register_handler(JobKind.AI_OVERVIEW, run_overview_job)
        register_handler(JobKind.AI_OVERVIEW_BATCH, run_overview_batch_job)
    except ValueError:
        pass
    try:
        with SessionLocal() as db:
            n = recover_zombie_jobs(db)
            if n:
                log.warning("Recovered %d zombie job(s) at startup", n)
    except Exception:
        log.exception("Zombie recovery failed (continuing)")
    # Hai worker chia theo LOẠI job (ADR #21 mục 5): worker kiểm tra loại trừ job
    # AI, worker AI chỉ nhận job AI → một lời gọi LLM không nằm chặn hàng đợi
    # kiểm tra. Cả hai cùng poll SQLite: ghi ngắn, WAL bật, và transaction ghi
    # của overview chỉ mở SAU khi LLM trả.
    job_worker = JobWorker(SessionLocal, exclude_kinds=AI_JOB_KINDS)
    job_worker.start()
    ai_worker = JobWorker(
        SessionLocal, name="audit-hq-ai-worker", kinds=AI_JOB_KINDS,
    )
    ai_worker.start()

    yield

    ai_worker.stop()
    job_worker.stop()
    retention_task.cancel()
    try:
        await retention_task
    except asyncio.CancelledError:
        pass


# `strip_empty_query_params` là phụ thuộc TOÀN CỤC nên nó chạy trước khi FastAPI kiểm
# kiểu tham số của từng hàm xử lý — `?year=` do giao diện dựng ra không còn thành lỗi.
# `register_error_handlers` là chỗ duy nhất quyết định lỗi ra HTML hay JSON (issue #94).
app = FastAPI(
    title="Audit-HQ MVP",
    version=VERSION,
    lifespan=lifespan,
    dependencies=[Depends(strip_empty_query_params)],
)
register_error_handlers(app)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(companies_router)
app.include_router(admin_router)
app.include_router(admin_ai_router)
app.include_router(admin_checks_router)
app.include_router(admin_risk_tiers_router)
app.include_router(admin_display_router)
app.include_router(admin_users_router)
app.include_router(admin_audit_router)
app.include_router(ai_router)
app.include_router(jobs_router)
app.include_router(docs_router)
app.include_router(catalog_router)
app.include_router(chat_page_router)


@app.get("/showcase", response_class=HTMLResponse)
def showcase() -> FileResponse:
    """Trang giới thiệu tính năng — CÔNG KHAI (không cần đăng nhập) để chia sẻ.

    File tĩnh self-contained sinh từ `.ai/features/2026-06-14-showcase/build_showcase.py`.
    """
    return FileResponse(BASE_DIR / "static" / "showcase.html", media_type="text/html")


@app.get("/on-bai", response_class=HTMLResponse)
def on_bai() -> FileResponse:
    """Runbook chuẩn bị demo (nội bộ) — CÔNG KHAI để chia sẻ cho team.

    File tĩnh self-contained. LƯU Ý: nội dung là tài liệu nội bộ (kịch bản, câu
    phản biện, ghi chú chuẩn bị) — trang để `noindex`; không link công khai.
    """
    return FileResponse(BASE_DIR / "static" / "on-bai.html", media_type="text/html")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "version": VERSION,
        "build_sha": BUILD_SHA,
        "build_time": BUILD_TIME,
    }


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


def _set_session_cookie(response: RedirectResponse, session_user: SessionUser) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        make_session_cookie(session_user),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 8,
    )


@app.post("/login", response_model=None)
def login_submit(
    request: Request,
    user: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    # Chống brute-force: khoá tạm theo IP sau nhiều lần sai.
    key = request.client.host if request.client else "?"
    wait = login_guard.locked_seconds(key)
    if wait:
        return templates.TemplateResponse(
            request, "login.html",
            {"error": f"Quá nhiều lần đăng nhập sai. Thử lại sau {wait} giây."},
            status_code=429,
        )

    session_user = login_with_credentials(db, user, password)
    if session_user is None:
        login_guard.record_failure(key)
        return templates.TemplateResponse(
            request, "login.html", {"error": "Sai tài khoản hoặc mật khẩu"}, status_code=401
        )
    login_guard.clear(key)
    response = RedirectResponse(url="/", status_code=303)
    _set_session_cookie(response, session_user)
    return response


@app.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/change-password", response_class=HTMLResponse)
def change_password_form(
    request: Request, user: SessionUser = Depends(require_user)
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "change_password.html",
        {"user": user, "error": None, "forced": user.must_change},
    )


@app.post("/change-password", response_model=None)
def change_password_submit(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    def _err(msg: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "change_password.html",
            {"user": user, "error": msg, "forced": user.must_change},
            status_code=400,
        )

    if len(new_password) < 8:
        return _err("Mật khẩu mới phải ít nhất 8 ký tự.")
    if new_password != confirm_password:
        return _err("Hai lần nhập mật khẩu không khớp.")

    row = get_user_by_username(db, user.name)
    if row is None:
        return _err("Tài khoản không tồn tại.")
    set_password(db, row, new_password, must_change=False)
    db.commit()

    # Cấp lại cookie không còn cờ buộc đổi → gỡ chặn require_user.
    fresh = SessionUser(name=user.name, role=user.role, must_change=False)
    response = RedirectResponse(url="/", status_code=303)
    _set_session_cookie(response, fresh)
    return response


@app.get("/", response_class=HTMLResponse)
def overview(request: Request, user: SessionUser = Depends(require_user)) -> HTMLResponse:
    return RedirectResponse(url="/companies", status_code=303)
