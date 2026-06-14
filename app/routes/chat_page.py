"""Trang /chat — trợ lý AI toàn trang (dedicated page).

API chat dùng lại router /api ở app/routes/ai.py. Trang này chỉ render khung HTML;
transcript + danh sách cuộc tải client-side qua /api. URL /chat/{id} cho phép
deep-link tới từng cuộc trò chuyện.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_user
from app.database import get_db
from app.models import AiConversation
from app.version import VERSION, version_string

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version"] = VERSION
templates.env.globals["app_version_string"] = version_string()


def _render(request: Request, user: SessionUser, conv_id: int | None) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "chat.html", {"user": user, "conv_id": conv_id, "hide_chat_fab": True}
    )


@router.get("/chat", response_class=HTMLResponse)
def chat_home(
    request: Request,
    user: SessionUser = Depends(require_user),
) -> HTMLResponse:
    return _render(request, user, None)


@router.get("/chat/{conv_id}", response_class=HTMLResponse)
def chat_conversation(
    conv_id: int,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    # 404 nếu cuộc không tồn tại hoặc ngoài quyền — không lộ tồn tại cuộc người khác.
    # Admin xem được của mọi user (giám sát); officer chỉ của chính mình.
    conv = db.get(AiConversation, conv_id)
    if conv is None or (conv.user != user.name and not user.is_admin):
        raise HTTPException(status_code=404, detail="Cuộc trò chuyện không tồn tại.")
    return _render(request, user, conv_id)
