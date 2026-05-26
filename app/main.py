import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.ai.config import seed_defaults as seed_ai_defaults
from app.ai.retention import run_retention_loop
from app.auth import (
    SESSION_COOKIE_NAME,
    SessionUser,
    login_with_credentials,
    make_session_cookie,
    require_user,
)
from app.auth_users import seed_default_admin
from app.database import SessionLocal, get_db
from app.jobs import register_handler
from app.jobs.handlers import run_batch_handler, run_checks_handler
from app.jobs.worker import JobWorker, recover_zombie_jobs
from app.models.job import JobKind
from app.routes.admin import router as admin_router
from app.routes.admin_ai import router as admin_ai_router
from app.routes.admin_users import router as admin_users_router
from app.routes.ai import router as ai_router
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
        with SessionLocal() as db:
            n = recover_zombie_jobs(db)
            if n:
                log.warning("Recovered %d zombie job(s) at startup", n)
    except Exception:
        log.exception("Zombie recovery failed (continuing)")
    job_worker = JobWorker(SessionLocal)
    job_worker.start()

    yield

    job_worker.stop()
    retention_task.cancel()
    try:
        await retention_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Audit-HQ MVP", version=VERSION, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(companies_router)
app.include_router(admin_router)
app.include_router(admin_ai_router)
app.include_router(admin_users_router)
app.include_router(ai_router)
app.include_router(jobs_router)
app.include_router(docs_router)


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


@app.post("/login", response_model=None)
def login_submit(
    request: Request,
    user: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    session_user = login_with_credentials(db, user, password)
    if session_user is None:
        return templates.TemplateResponse(
            request, "login.html", {"error": "Sai tài khoản hoặc mật khẩu"}, status_code=401
        )
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        make_session_cookie(session_user),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 8,
    )
    return response


@app.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
def overview(request: Request, user: SessionUser = Depends(require_user)) -> HTMLResponse:
    return RedirectResponse(url="/companies", status_code=303)
