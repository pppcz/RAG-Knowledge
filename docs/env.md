# 运行环境与已知问题

## 1. 版本要求

| 组件 | 版本 |
| --- | --- |
| Python | 3.12（由 uv 管理，`.python-version` 固定） |
| uv | 0.13 及以上 |
| Node.js | 20 及以上 |
| Docker Engine | 24 及以上 |
| Docker Compose | v2 及以上 |
| PostgreSQL | 16（`pgvector/pgvector:pg16` 镜像内置） |
| Redis | 7 |
| MinIO | 最新稳定版 |

Python 侧依赖以 `pyproject.toml` 与 `uv.lock` 为准，执行 `uv sync` 后安装到 `.venv`：

```text
fastapi           uvicorn            starlette
pydantic          pydantic-settings  sqlalchemy[asyncio]
alembic           psycopg            sse-starlette
pypdf             python-docx        markdown
pytest            pytest-asyncio     httpx
ruff
```

前端依赖以 `frontend/package.json` 与 `package-lock.json` 为准。

## 2. 端口规划

| 用途 | 宿主端口 | 容器端口 | 说明 |
| --- | --- | --- | --- |
| PostgreSQL（pgvector） | **5433** | 5432 | 固定 5433 |
| Redis | 6379 | 6379 | |
| MinIO S3 API | 9000 | 9000 | |
| MinIO Console | 9001 | 9001 | <http://localhost:9001> |
| 后端 Uvicorn（本地开发） | 8000 | — | |
| 前端（Nginx 容器） | 8080 | 80 | |

PostgreSQL 之所以映射到 5433 而不是默认的 5432，是因为开发机上常已存在本地
PostgreSQL 服务占用 5432。避开该端口后 compose 可以直接启动，不需要停用系统服务或调整
既有数据库。若 5433 也被占用，改 `docker-compose.yml` 的端口映射并同步 `DATABASE_URL` 即可。

## 3. 数据库初始化

首次启动容器后执行迁移：

```powershell
uv run alembic upgrade head      # 建表 + 创建 vector 扩展 + HNSW 索引
uv run alembic current           # 查看当前版本
```

迁移文件与表结构说明见 [database.md](database.md)。

## 4. 已知问题与规避方式

### 4.1 Windows 上 psycopg 不支持 ProactorEventLoop

- 现象：`uv run pytest` 或种子脚本报
  `Psycopg cannot use the 'ProactorEventLoop' to run in async mode`。
- 原因：Windows 默认事件循环是 `ProactorEventLoop`，psycopg 的异步驱动只支持
  `SelectorEventLoop`；uvicorn 仅在 reload 或多 worker 子进程模式下才使用 Selector。
- 规避：本地启动后端统一带 `--reload`：

  ```powershell
  uv run uvicorn app.main:app --reload
  ```

  `app/core/asyncio_compat.py` 提供 `SelectorEventLoop` 运行入口，种子脚本与
  `tests/conftest.py` 均已切换到该策略。Linux 容器默认使用 selectors，不受影响。

### 4.2 PowerShell 5.1 的编码与引号问题

- 现象一：含中文的 `.ps1` 在 Windows PowerShell 5.1 下按 ANSI 读取，报
  `The string is missing the terminator` 等语法错误。
- 现象二：`curl.exe -d '{"username":"admin"}'` 在 5.1 下双引号被吞掉，JSON 非法导致 400。
- 规避：`scripts/*.ps1` 保持纯 ASCII，中文说明写在 `docs/`；需要传 JSON 时写入临时文件，
  用 `curl.exe -d "@file"` 传递。HTTP 命令统一写 `curl.exe`，避免 PowerShell 的 `curl` 别名。

### 4.3 `alembic.ini` 的中文注释导致解析失败

- 现象：`alembic.ini` 被 `configparser` 按系统区域编码（如 GBK）读取，中文注释触发
  `UnicodeDecodeError`。
- 规避：`alembic.ini` 只保留 ASCII 注释，中文说明放在 `docs/` 与代码 docstring 中。

### 4.4 Docker 镜像拉取失败

- 现象：`docker compose up -d` 卡在拉取镜像，报 `502 Bad Gateway` 或连接超时。
- 规避：在 Docker Desktop 的 Settings → Docker Engine 中配置可用的
  `registry-mirrors`，保存后重启 Docker。镜像源可用性会变化，用
  `docker pull hello-world` 验证加速器是否对 daemon 生效。

### 4.5 SSE 经 Nginx 反代后变成一次性返回

- 现象：本地直连后端时流式正常，走 Nginx 后所有内容在结束时一次性吐出。
- 原因：Nginx 默认开启响应缓冲。
- 规避：`deploy/nginx.conf` 中对 `/api` 设置 `proxy_buffering off`、`proxy_read_timeout`
  调大，并关闭上游压缩。

## 5. 环境变量

完整变量表见 [deploy.md](deploy.md)。本地开发复制模板即可：

```powershell
Copy-Item .env.example .env
```

`.env` 永不提交，`.env.example` 只放占位符。
