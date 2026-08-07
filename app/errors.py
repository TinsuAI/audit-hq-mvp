"""Trang lỗi dùng chung — trình duyệt nhận HTML tiếng Việt, mã gọi API nhận JSON.

Trước đây ứng dụng không đăng ký trình xử lý lỗi nào, nên mọi lỗi đều đổ JSON của
framework thẳng ra màn hình cán bộ: gõ sai mã doanh nghiệp, mở DN ngoài phạm vi
được phân công, đường dẫn file sai, hay bất kỳ lỗi hệ thống nào (issue #94).

Hai việc tách bạch trong file này:

1. `strip_empty_query_params` — tham số số nguyên CÓ MẶT nhưng RỖNG (`?year=`) được
   coi như không truyền. Giao diện dựng liên kết bằng `?year={{ ... or '' }}` nên một
   công việc không gắn kỳ sinh ra `?year=`; khai báo `int | None = Query(default=None)`
   chấp nhận vắng mặt chứ không chấp nhận chuỗi rỗng. Xử lý ở một chỗ dùng chung, KHÔNG
   sửa từng khai báo, để tham số thêm về sau không lọt lại.
2. Ba trình xử lý lỗi + `error.html`. Điều kiện chọn JSON hay HTML nằm ở `_wants_json`:
   đường dẫn `.json` và `/api/` luôn là JSON vì có JavaScript đang đọc (`overview-poll.js`
   poll `overview.json`, thanh điều hướng poll `unread.json`, sidebar gọi `/api/chat/*`)
   — trả HTML cho các điểm cuối đó là hỏng im lặng.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date, datetime, time
from decimal import Decimal
from http import HTTPStatus
from pathlib import Path
from typing import Any, get_args, get_origin
from urllib.parse import urlencode
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.templating import Jinja2Templates
from starlette.datastructures import QueryParams
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.auth import read_session
from app.version import VERSION, version_string

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version"] = VERSION
templates.env.globals["app_version_string"] = version_string()


# --- Tham số số nguyên rỗng = không truyền ------------------------------------

# Danh sách CHO PHÉP, không phải danh sách cấm: chỉ bỏ chuỗi rỗng khi chắc chắn kiểu
# không nhận chuỗi. Kiểu lạ → giữ nguyên, lúc đó lỗi vẫn ra trang tiếng Việt.
_EMPTY_MEANS_ABSENT_TYPES = (int, float, bool, Decimal, date, datetime, time, UUID)


def _empty_means_absent(annotation: Any) -> bool:
    """Kiểu này có coi chuỗi rỗng là vô nghĩa không? `int | None` có, `str | None` không."""
    if get_origin(annotation) is None:
        return isinstance(annotation, type) and issubclass(annotation, _EMPTY_MEANS_ABSENT_TYPES)
    args = [a for a in get_args(annotation) if a is not type(None)]
    return bool(args) and all(_empty_means_absent(a) for a in args)


def _query_fields(dependant: Any) -> Iterator[Any]:
    """Tham số truy vấn của route VÀ của mọi phụ thuộc lồng bên trong.

    Một phụ thuộc dùng chung (vd bộ lọc phân trang) khai tham số của riêng nó; quét
    thiếu nhánh này thì tham số thêm sau sẽ lọt đúng như lỗi ban đầu.
    """
    yield from dependant.query_params
    for sub in dependant.dependencies:
        yield from _query_fields(sub)


def strip_empty_query_params(request: Request) -> None:
    """Bỏ tham số truy vấn rỗng khỏi yêu cầu, trước khi FastAPI kiểm kiểu.

    Chạy như một phụ thuộc toàn cục nên nó được giải TRƯỚC tham số của chính hàm xử
    lý. `request.scope["route"]` cho biết kiểu đã khai của từng tham số, nhờ đó chỉ
    tham số kiểu số mới bị bỏ — `?q=` vẫn là chuỗi rỗng đúng như trước.
    """
    raw = request.scope.get("query_string") or b""
    if b"=" not in raw:
        return
    dependant = getattr(request.scope.get("route"), "dependant", None)
    if dependant is None:
        return
    try:
        droppable = {
            (field.alias or field.name)
            for field in _query_fields(dependant)
            if _empty_means_absent(field.field_info.annotation)
        }
    except Exception:
        # Kiểu lạ thì giữ nguyên yêu cầu: lỗi vẫn ra trang tiếng Việt, chỉ là không
        # được bỏ qua tham số rỗng. Đoán sai kiểu nguy hiểm hơn.
        log.debug("Không đọc được kiểu tham số truy vấn của %s", request.url.path, exc_info=True)
        return
    if not droppable:
        return

    items = request.query_params.multi_items()
    kept = [(k, v) for k, v in items if not (v == "" and k in droppable)]
    if len(kept) == len(items):
        return
    request.scope["query_string"] = urlencode(kept).encode()
    request._query_params = QueryParams(kept)


# --- Câu chữ tiếng Việt cho từng mã trạng thái --------------------------------

_TITLES: dict[int, str] = {
    400: "Yêu cầu không hợp lệ",
    401: "Phiên làm việc đã hết hạn",
    403: "Không đủ quyền truy cập",
    404: "Không tìm thấy nội dung",
    405: "Thao tác không áp dụng cho địa chỉ này",
    409: "Dữ liệu vừa thay đổi ở nơi khác",
    413: "Tệp tải lên quá lớn",
    422: "Địa chỉ trang không hợp lệ",
    429: "Thao tác quá nhanh",
    500: "Hệ thống gặp sự cố",
    503: "Chức năng tạm thời chưa sẵn sàng",
}

_MESSAGES: dict[int, str] = {
    400: "Yêu cầu gửi lên không đúng định dạng nên hệ thống chưa xử lý được.",
    401: "Phiên làm việc đã kết thúc. Quý vị vui lòng đăng nhập lại để tiếp tục.",
    403: "Tài khoản của quý vị không được cấp quyền mở nội dung này.",
    404: (
        "Nội dung quý vị tìm không tồn tại, đã được xoá, hoặc nằm ngoài phạm vi "
        "doanh nghiệp được phân công cho tài khoản này."
    ),
    405: "Địa chỉ này không nhận thao tác vừa thực hiện.",
    409: "Dữ liệu vừa được thay đổi ở nơi khác. Quý vị vui lòng tải lại trang rồi thao tác lại.",
    413: "Tệp vượt quá dung lượng cho phép. Quý vị vui lòng tách nhỏ tệp rồi tải lên lại.",
    422: "Địa chỉ trang chứa tham số không hợp lệ nên hệ thống chưa mở được trang.",
    429: "Hệ thống nhận quá nhiều yêu cầu trong thời gian ngắn. Quý vị vui lòng chờ một lát rồi thử lại.",
    500: (
        "Hệ thống gặp sự cố khi xử lý yêu cầu. Sự việc đã được ghi vào nhật ký kỹ thuật "
        "để bộ phận quản trị xem xét. Quý vị vui lòng thử lại sau ít phút."
    ),
    503: "Chức năng này đang tạm ngưng. Quý vị vui lòng thử lại sau.",
}

# Nhãn tiếng Việt cho tham số trên địa chỉ. Không có nhãn thì không nêu tên tham số —
# tên định danh tiếng Anh không được hiện ra màn hình.
_PARAM_LABELS: dict[str, str] = {
    "year": "năm",
    "page": "trang",
    "ingested": "trạng thái vừa nạp",
    "check": "mã kiểm tra",
    "book": "sổ quyết toán",
    "sheet": "trang tính",
    "limit": "số dòng mỗi trang",
    "offset": "vị trí bắt đầu",
    "table": "bảng dữ liệu",
    "status": "trạng thái",
    "q": "từ khoá",
    "date_from": "ngày bắt đầu",
    "date_to": "ngày kết thúc",
    "decl_no": "số tờ khai",
    "customs": "loại hình",
    "company": "doanh nghiệp",
    "company_id": "doanh nghiệp",
    "company_code": "doanh nghiệp",
    "kind": "loại công việc",
    "family": "nhóm kiểm tra",
    "add": "số dòng thêm",
    "job_id": "số hiệu công việc",
    "conv_id": "cuộc trao đổi",
}


def _text_for(status_code: int) -> tuple[str, str]:
    fallback = 500 if status_code >= 500 else 400
    title = _TITLES.get(status_code) or _TITLES[fallback]
    message = _MESSAGES.get(status_code) or _MESSAGES[fallback]
    return title, message


# --- Chọn HTML hay JSON -------------------------------------------------------

# Điểm cuối có JavaScript đọc `.json()`. Trả HTML cho chúng làm hỏng poll im lặng.
_JSON_PATH_PREFIXES = ("/api/",)


def _wants_json(request: Request) -> bool:
    path = request.url.path
    if path.endswith(".json") or path.startswith(_JSON_PATH_PREFIXES):
        return True
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        return True
    return "text/html" not in request.headers.get("accept", "")


# --- Dựng phản hồi ------------------------------------------------------------

_MINIMAL_PAGE = (
    '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
    "<title>{title} — Audit-HQ</title></head><body>"
    "<h1>{title}</h1><p>{message}</p>"
    '<p><a href="/companies">Về danh sách doanh nghiệp</a></p>'
    "</body></html>"
)


def _back_links(request: Request, status_code: int) -> list[dict[str, str]]:
    """Đường quay lại. Không trỏ về chính trang vừa 404, tránh vòng lặp."""
    links: list[dict[str, str]] = []
    parts = [p for p in request.url.path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "companies" and status_code != 404:
        links.append({"url": f"/companies/{parts[1]}", "label": "Về trang doanh nghiệp"})
    links.append({"url": "/companies", "label": "Về danh sách doanh nghiệp"})
    return links


def _render(
    request: Request,
    status_code: int,
    *,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    json_body: Any = None,
) -> Response:
    title, message = _text_for(status_code)
    if _wants_json(request):
        body = json_body if json_body is not None else {"detail": detail or message}
        return JSONResponse(body, status_code=status_code, headers=headers)
    try:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "user": read_session(request),
                "status_code": status_code,
                "error_title": title,
                "error_message": message,
                "error_detail": detail,
                "back_links": _back_links(request, status_code),
                "hide_chat_fab": True,
            },
            status_code=status_code,
            headers=headers,
        )
    except Exception:
        log.exception("Không dựng được trang lỗi cho %s", request.url.path)
        return HTMLResponse(
            _MINIMAL_PAGE.format(title=title, message=message),
            status_code=status_code,
            headers=headers,
        )


def _safe_detail(exc: StarletteHTTPException) -> str | None:
    """Câu giải thích kèm theo lỗi, đã lọc câu mặc định tiếng Anh của framework."""
    detail = exc.detail
    if not isinstance(detail, str) or not detail.strip():
        return None
    try:
        if detail.strip() == HTTPStatus(exc.status_code).phrase:
            return None
    except ValueError:
        pass
    return detail.strip()


# --- Ba trình xử lý -----------------------------------------------------------


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    headers = exc.headers or None
    # `require_user` báo chưa đăng nhập bằng 303 kèm Location — giữ nguyên chuyển
    # hướng, đừng biến nó thành trang lỗi.
    if 300 <= exc.status_code < 400:
        lowered = {k.lower(): v for k, v in (exc.headers or {}).items()}
        location = lowered.get("location")
        if location:
            return RedirectResponse(location, status_code=exc.status_code)

    detail = _safe_detail(exc)
    if exc.status_code >= 500:
        # Câu kèm theo lỗi 500 hay chứa thông điệp của ngoại lệ gốc (vd "Lưu file lỗi: …")
        # — vào nhật ký, không ra màn hình.
        log.error(
            "HTTPException %s tại %s %s: %s",
            exc.status_code, request.method, request.url.path, detail,
        )
        detail = None
    return _render(request, exc.status_code, detail=detail, headers=headers)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> Response:
    labels: list[str] = []
    for err in exc.errors():
        loc = err.get("loc") or ()
        if len(loc) >= 2 and loc[0] in ("query", "path"):
            label = _PARAM_LABELS.get(str(loc[-1]))
            if label and label not in labels:
                labels.append(label)
    detail = f"Giá trị không hợp lệ ở tham số: {', '.join(labels)}." if labels else None
    # Mã gọi API giữ nguyên dạng thân phản hồi cũ của FastAPI.
    return _render(
        request,
        422,
        detail=detail,
        json_body={"detail": jsonable_encoder(exc.errors())},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    """Lỗi ngoài dự kiến: dấu vết ngăn xếp chỉ vào nhật ký, người dùng thấy lời xin lỗi."""
    log.exception("Lỗi chưa xử lý tại %s %s", request.method, request.url.path)
    return _render(request, 500)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
