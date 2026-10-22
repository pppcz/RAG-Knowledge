# 部署文档

## 1. 前置要求

| 组件 | 要求 |
| --- | --- |
| Docker Desktop | 已启动（Windows / macOS / Linux 均可） |
| Docker Compose | v2+（`docker compose` 子命令） |
| 宿主端口 | `8080`（前端）、`8000`（后端）、`5433`（PostgreSQL）、`6379`（Redis）、`9000/9001`（MinIO） |
| 资源建议 | 2 CPU / 4 GB 内存以上（镜像构建需要更多） |

> 开发机上 `5432` 常已被本地 PostgreSQL 占用，因此本项目 PostgreSQL 固定映射到 **5433**。

## 2. 一键启动

```powershell
# 1) 准备环境变量（.env 不提交，含密钥与本地凭据）
Copy-Item .env.example .env

# 2) 构建并启动全部服务（postgres / redis / minio / backend / frontend）
docker compose up -d --build

# 3) 查看状态（等 backend、frontend 变 healthy）
docker compose ps

# 4) 访问
#    前端：http://localhost:8080
#    后端文档：http://localhost:8000/docs
#    健康检查：http://localhost:8000/health
curl.exe http://localhost:8080/health
curl.exe http://localhost:8080/
```

也可以用脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

首次启动时后端容器会：

1. 执行 `alembic upgrade head`（建表 / 加 pgvector 扩展与向量索引）
2. 当 `SEED_DEFAULT_DATA=true` 时创建默认租户与管理员 `admin / 123456`
3. 启动 uvicorn（`WORKERS` 默认 1）

登录：浏览器打开 <http://localhost:8080>，使用 `admin / 123456`。

## 3. 服务与端口

| 服务 | 镜像 | 宿主端口 | 说明 |
| --- | --- | --- | --- |
| `postgres` | `pgvector/pgvector:pg16` | 5433 → 5432 | 数据库 + 向量 |
| `redis` | `redis:7` | 6379 | 缓存（预留） |
| `minio` | `minio/minio` | 9000 / 9001 | 对象存储 / 控制台 |
| `backend` | 本地构建（`deploy/Dockerfile` target `backend`） | 8000 | FastAPI |
| `frontend` | 本地构建（`deploy/Dockerfile` target `frontend`） | 8080 → 80 | Nginx + 静态资源 |

数据卷：`rag-pgdata`、`rag-redisdata`、`rag-miniodata`（命名卷，`docker compose down -v` 会清空）。

## 4. 环境变量

完整模板见 [`.env.example`](../.env.example)。

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `APP_ENV` | 运行环境 | `dev` |
| `SECRET_KEY` | JWT 签名密钥，**生产必须替换** | `change-me` |
| `DATABASE_URL` | 本地开发用（`localhost:5433`）；compose 中覆盖为 `postgres:5432` | — |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `MINIO_*` | MinIO 地址与凭据 | `localhost:9000` / `minioadmin` |
| `STORAGE_PROVIDER` | `minio` 或 `local`（离线降级） | `minio` |
| `MAX_UPLOAD_MB` | 单文件上限 | `20` |
| `POSTGRES_USER/PASSWORD/DB` | 容器初始化凭据 | `rag/rag/rag` |
| `SEED_DEFAULT_DATA` | 后端启动时是否创建默认租户/管理员 | `true`（生产请 `false`） |
| `LLM_PROVIDER` | `mock` 或 `openai_compatible` | `mock` |
| `EMBEDDING_PROVIDER` | `hash` 或 `openai_compatible` | `hash` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` / `TOP_K` | RAG 参数 | `800` / `120` / `5` |

## 5. 本地开发模式（不走容器后端）

```powershell
docker compose up -d postgres redis minio   # 只起基础设施
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed
uv run uvicorn app.main:app --reload        # 必须带 --reload（Windows 事件循环）
cd frontend; npm install; npm run dev        # http://localhost:5173
```

## 6. 常用运维命令

```powershell
docker compose ps                       # 状态
docker compose logs -f backend          # 后端日志
docker compose restart backend          # 重启后端
docker compose down                     # 停止（保留数据卷）
docker compose down -v                  # 停止并清空数据（谨慎）
docker compose exec backend alembic current          # 当前迁移版本
docker compose exec backend python -m scripts.seed   # 手动补种子数据
docker compose exec postgres psql -U rag -d rag      # 进库
```

## 7. 常见问题

**Q1：`docker compose up` 拉镜像失败 / 502**
镜像加速器问题。Docker Desktop → Settings → Docker Engine 里配置可用的
`registry-mirrors`，然后重启 Docker。

**Q2：PostgreSQL 端口冲突**
若宿主 `5432` 已被其它 PostgreSQL 占用，本项目固定用 `5433`；如 `5433` 也被占用，请改用其它端口并同步 `DATABASE_URL`。

**Q3：`npm run build` 报 esbuild `Access is denied`（Windows）**
`C:\WINDOWS\TEMP` 对当前用户不可写。`frontend/vite.config.ts` 已自动把临时目录指向
`frontend/.tmp`，无需手工处理；若仍失败请检查该目录权限。

**Q4：本地 `uv run uvicorn app.main:app` 报 `Psycopg cannot use the 'ProactorEventLoop'`**
Windows 必须带 `--reload`（或 `--workers 2`）让 uvicorn 使用 SelectorEventLoop；
容器内是 Linux，不受影响。

**Q5：问答不是流式的**
Nginx 必须关闭 `proxy_buffering`（已在 `deploy/nginx.conf` 配置），
反向代理/CDN 上也要关闭缓冲。

**Q6：上传大文件返回 413**
同时调整 `MAX_UPLOAD_MB`（后端）、`client_max_body_size`（Nginx，默认 25m）。

## 8. 生产建议

1. `SECRET_KEY` 换成 32 字节以上随机串（`python -c "import secrets;print(secrets.token_hex(32))"`）。
2. `SEED_DEFAULT_DATA=false`，删除默认账号或改强密码。
3. `POSTGRES_PASSWORD`、`MINIO_SECRET_KEY` 换强口令，凭据只走环境变量 / 密钥管理。
4. 前面再加一层带 HTTPS 的反向代理（Caddy / Traefik），或给 Nginx 配证书。
5. `WORKERS` 按 CPU 数调整；必要时把解析/向量化改为后台任务。
6. 定期备份 `rag-pgdata` 卷与 MinIO 桶。
7. 监控 `/health`，并把容器日志接入集中日志系统。
