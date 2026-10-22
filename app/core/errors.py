"""统一错误响应：{"code": int, "message": str, "detail": {...}}。"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# 业务错误码：错误码前 3 位与 HTTP 状态码对应，末 2 位为细分码
CODE_BY_STATUS: dict[int, int] = {
    400: 40001,
    401: 40101,
    403: 40301,
    404: 40401,
    405: 40501,
    409: 40901,
    413: 41301,
    415: 41501,
    422: 40001,
    429: 42901,
    500: 50001,
}


class AppError(Exception):
    """业务异常，由全局处理器转换为统一错误结构。"""

    def __init__(
        self,
        code: int,
        message: str,
        status_code: int = 400,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail: dict[str, Any] = detail or {}


def error_response(
    status_code: int,
    code: int,
    message: str,
    detail: Any = None,
) -> JSONResponse:
    """构造统一错误响应。"""
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "detail": detail if detail is not None else {},
        },
    )


def _normalize_validation_errors(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """裁剪 pydantic 错误信息，保证可 JSON 序列化。"""
    normalized: list[dict[str, Any]] = []
    for item in raw:
        normalized.append(
            {
                "loc": [str(part) for part in item.get("loc", [])],
                "msg": str(item.get("msg", "")),
                "type": str(item.get("type", "")),
            }
        )
    return normalized


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器，保证所有错误都是统一结构。"""

    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            422,
            40001,
            "请求参数校验失败",
            {"errors": _normalize_validation_errors(exc.errors())},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = CODE_BY_STATUS.get(exc.status_code, exc.status_code * 100)
        if isinstance(exc.detail, str):
            return error_response(exc.status_code, code, exc.detail)
        return error_response(exc.status_code, code, "请求失败", {"info": exc.detail})

    @app.exception_handler(Exception)
    async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常: %s", exc)
        return error_response(500, 50001, "服务器内部错误")
