from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import (
    SESSION_COOKIE_NAME,
    check_credentials,
    make_session_cookie,
    require_user,
)
from app.routes.admin import router as admin_router
from app.routes.companies import router as companies_router
from app.version import BUILD_SHA, BUILD_TIME, VERSION, version_string

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version"] = VERSION
templates.env.globals["app_version_string"] = version_string()
templates.env.globals["app_build_sha"] = BUILD_SHA
templates.env.globals["app_build_time"] = BUILD_TIME

app = FastAPI(title="Audit-HQ MVP", version=VERSION)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(companies_router)
app.include_router(admin_router)


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
) -> HTMLResponse | RedirectResponse:
    if not check_credentials(user, password):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Sai tài khoản hoặc mật khẩu"}, status_code=401
        )
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        make_session_cookie(user),
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
def overview(request: Request, user: str = Depends(require_user)) -> HTMLResponse:
    return RedirectResponse(url="/companies", status_code=303)
