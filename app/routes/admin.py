"""Admin routes — quản lý hệ thống UOM (canonical + alias).

Mục đích: cán bộ HQ / Trọng Tín / dev bổ sung alias hoặc canonical mới khi
gặp đơn vị tính lạ trong dữ liệu DN, không cần đụng code.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_admin
from app.checks.uom import invalidate_cache
from app.database import get_db
from app.models import UomAlias, UomCanonical
from app.version import VERSION, version_string

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version_string"] = version_string()
templates.env.globals["app_version"] = VERSION

router = APIRouter(prefix="/admin")


_FAMILIES = [
    "length", "mass", "area", "volume",
    "count", "count_packaging", "time", "energy",
]


@router.get("/units", response_class=HTMLResponse)
def units_list(
    request: Request,
    family: str | None = Query(default=None),
    q: str | None = Query(default=None),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """List canonical units (grouped by family) + alias count per canonical."""
    canon_query = select(UomCanonical).order_by(UomCanonical.family, UomCanonical.code)
    if family:
        canon_query = canon_query.where(UomCanonical.family == family)
    if q:
        canon_query = canon_query.where(UomCanonical.code.contains(q.upper()))
    canonicals = db.scalars(canon_query).all()

    # Aliases grouped by canonical_code.
    alias_rows = db.execute(
        select(UomAlias.canonical_code, UomAlias.alias).order_by(UomAlias.alias)
    ).all()
    aliases_by_code: dict[str, list[str]] = defaultdict(list)
    for code, alias in alias_rows:
        aliases_by_code[code].append(alias)

    families_grouped: dict[str, list] = defaultdict(list)
    for c in canonicals:
        families_grouped[c.family].append({
            "row": c,
            "aliases": aliases_by_code.get(c.code, []),
        })

    # Stats
    total_canonical = db.scalar(select(func.count()).select_from(UomCanonical))
    total_aliases = db.scalar(select(func.count()).select_from(UomAlias))

    return templates.TemplateResponse(
        request,
        "admin_units.html",
        {
            "user": user,
            "families_grouped": dict(families_grouped),
            "families": _FAMILIES,
            "filter_family": family,
            "q": q,
            "total_canonical": total_canonical,
            "total_aliases": total_aliases,
        },
    )


@router.post("/units/aliases")
def units_add_alias(
    alias: str = Form(...),
    canonical_code: str = Form(...),
    note: str = Form(""),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Thêm alias mới. Nếu alias đã tồn tại → 400."""
    alias_norm = alias.strip().upper()
    code_norm = canonical_code.strip().upper()
    if not alias_norm:
        raise HTTPException(status_code=400, detail="Bí danh không được trống")
    if db.scalar(select(UomCanonical).where(UomCanonical.code == code_norm)) is None:
        raise HTTPException(status_code=400, detail=f"Đơn vị chuẩn {code_norm!r} không tồn tại")
    if db.scalar(select(UomAlias).where(UomAlias.alias == alias_norm)) is not None:
        raise HTTPException(status_code=400, detail=f"Bí danh {alias_norm!r} đã có")

    db.add(UomAlias(alias=alias_norm, canonical_code=code_norm, note=note.strip() or None))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Lỗi cơ sở dữ liệu khi thêm bí danh") from None

    invalidate_cache()
    return RedirectResponse(url=f"/admin/units?q={alias_norm}", status_code=303)


@router.post("/units/aliases/{alias_id}/delete")
def units_delete_alias(
    alias_id: int,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    row = db.get(UomAlias, alias_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Bí danh không tồn tại")
    db.delete(row)
    db.commit()
    invalidate_cache()
    return RedirectResponse(url="/admin/units", status_code=303)


@router.post("/units/canonical")
def units_add_canonical(
    code: str = Form(...),
    family: str = Form(...),
    base_factor: float = Form(1.0),
    name_vi: str = Form(""),
    description: str = Form(""),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    code_norm = code.strip().upper()
    if not code_norm:
        raise HTTPException(status_code=400, detail="Mã đơn vị không được trống")
    if family not in _FAMILIES:
        raise HTTPException(status_code=400, detail=f"Nhóm đơn vị không hợp lệ: {family}")
    if db.scalar(select(UomCanonical).where(UomCanonical.code == code_norm)) is not None:
        raise HTTPException(status_code=400, detail=f"Đơn vị chuẩn {code_norm!r} đã có")

    db.add(UomCanonical(
        code=code_norm, family=family, base_factor=base_factor,
        name_vi=name_vi.strip() or None,
        description=description.strip() or None,
    ))
    # Tự auto-add alias = code (canonical luôn là alias của chính nó).
    db.add(UomAlias(alias=code_norm, canonical_code=code_norm, note="auto-created"))
    db.commit()
    invalidate_cache()
    return RedirectResponse(url=f"/admin/units?family={family}", status_code=303)
