#!/bin/sh
# 后端容器入口：迁移 → 可选种子数据 → uvicorn
set -e

echo "[entrypoint] 执行数据库迁移 alembic upgrade head"
alembic upgrade head

if [ "${SEED_DEFAULT_DATA:-false}" = "true" ]; then
    echo "[entrypoint] 初始化默认租户与管理员（SEED_DEFAULT_DATA=true）"
    python -m scripts.seed
fi

echo "[entrypoint] 启动 uvicorn workers=${WORKERS:-1} port=${PORT:-8000}"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WORKERS:-1}" \
    --proxy-headers \
    --forwarded-allow-ips '*'
