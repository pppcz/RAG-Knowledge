# syntax=docker/dockerfile:1
# 单文件多阶段构建：
#   backend-builder -> backend    （compose 中 target: backend）
#   frontend-builder -> frontend  （compose 中 target: frontend）
# 构建上下文为仓库根目录：docker build -f deploy/Dockerfile --target backend .

# ============================================================
# 后端：安装依赖
# ============================================================
FROM python:3.12-slim AS backend-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# 使用官方 uv 静态二进制（固定版本，避免在镜像里装 Python 包管理器）
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

WORKDIR /app

# 先只拷贝依赖描述，最大化利用构建缓存
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

# ============================================================
# 后端：运行镜像
# ============================================================
FROM python:3.12-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000 \
    WORKERS=1

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app

COPY --from=backend-builder /app/.venv /app/.venv
COPY --from=backend-builder /app/app /app/app
COPY --from=backend-builder /app/alembic /app/alembic
COPY --from=backend-builder /app/alembic.ini /app/alembic.ini
COPY --from=backend-builder /app/scripts /app/scripts

COPY deploy/entrypoint.sh /app/deploy/entrypoint.sh
RUN chmod +x /app/deploy/entrypoint.sh && chown -R app:app /app

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

ENTRYPOINT ["/app/deploy/entrypoint.sh"]

# ============================================================
# 前端：构建静态资源
# ============================================================
FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ============================================================
# 前端：Nginx 托管
# ============================================================
FROM nginx:1.27-alpine AS frontend

COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-builder /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
