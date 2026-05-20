import secrets

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeSerializer

from app.settings import settings

_SESSION_KEY = "ahq_session"
_signer = URLSafeSerializer(settings.session_secret, salt="ahq-auth")


def make_session_cookie(user: str) -> str:
    return _signer.dumps({"u": user})


def read_session(request: Request) -> str | None:
    raw = request.cookies.get(_SESSION_KEY)
    if not raw:
        return None
    try:
        data = _signer.loads(raw)
    except BadSignature:
        return None
    return data.get("u")


def check_credentials(user: str, password: str) -> bool:
    return secrets.compare_digest(user, settings.auth_user) and secrets.compare_digest(
        password, settings.auth_password
    )


def require_user(request: Request) -> str:
    user = read_session(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


SESSION_COOKIE_NAME = _SESSION_KEY
