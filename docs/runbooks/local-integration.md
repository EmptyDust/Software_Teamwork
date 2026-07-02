# 本地联调运行手册

日期：2026-06-29

本文记录当前仓库可以怎样在本地启动、验证和排查服务。它不是生产部署说明；根级 `deploy/docker-compose.yml` 只作为本地/演示联调基线，不等同于已经具备完整一键 E2E smoke。生产或准生产单机 Compose 基线见 [`deploy/production-baseline.md`](../../deploy/production-baseline.md)、`deploy/docker-compose.production.yml` 和 `deploy/.env.production.example`。

## 当前结论

| 范围 | 当前状态 | 说明 |
| --- | --- | --- |
| 根级本地/演示 Compose | partial | `deploy/docker-compose.yml` 已提供共享 PostgreSQL、Redis、Parser、服务 migration、`seed-local` / `seed-local-ai` 和基础服务串联；Compose 也会启动 Qdrant/MinIO 容器，并通过 `minio-init` 创建本地 File Service 内部 bucket `software-teamwork-local`。默认 Knowledge 使用 in-memory vector index、File 容器使用 local storage；File 的 PostgreSQL + MinIO 路径通过显式 env-gated smoke 验证。当前 seed data 覆盖本地 admin 登录、Knowledge 示例库/文档/分块、Document 报告样例、QA 会话样例，以及可选 AI profile placeholder；这仍只是本地联调基线，不等同于完整一键 E2E smoke。 |
| QA 服务 Compose | partial | `services/qa/docker-compose.yml` 会启动 QA PostgreSQL、Auth PostgreSQL、Redis、Auth、QA 和 Gateway；不包含 Knowledge、Document、File、AI Gateway。 |
| Document 服务 Compose | partial | `services/document/docker-compose.yml` 会启动 Document PostgreSQL、Redis、migration 和 Document；不包含 File、AI Gateway。 |
| AI Gateway 本地运行 | root profile / host-run | 根级 `docker compose --profile ai` 会启动 AI Gateway、migration 和 placeholder profile seed；单独调试时也可 host-run，真实 provider smoke 仍需配置有效 provider key。 |
| File / Knowledge 独立运行 | host-run / smoke | 需要手动准备各自依赖；File 已有 env-gated PostgreSQL + MinIO 联合 smoke，Knowledge 已有 env-gated ingestion 真实依赖 smoke，覆盖 File Service、Parser Service、PostgreSQL、local hashing embedding 和 Qdrant 写入。另有 env-gated Gateway -> Knowledge -> QA RAG smoke，可在配置可用 AI Gateway chat profile 后验收上传、入库、`knowledge-queries`、QA answer 和 citations；MCP 和完整 #125 一键跨服务 smoke 仍由后续任务覆盖。 |
| Parser Runtime | partial | `services/parser/` 已提供 Python/FastAPI runtime、内部 HTTP API、Dockerfile、service-token auth、可选 PaddleOCR extra 和 env-gated 真实 PaddleOCR 模型 smoke；CI 仍只用 fake OCR backend 覆盖 lint/test/compile，不要求普通开发者安装模型。 |
| 前端联调入口 | host-run | 前端只调用 public Gateway `/api/v1/**`；不要直连内部服务。 |
| 生产/准生产 Compose | baseline docs | `deploy/production-baseline.md`、`deploy/docker-compose.production.yml` 和 `deploy/.env.production.example` 已提供单机 Compose 基线、环境变量模板、持久化卷、secret、健康检查、升级和回滚说明；真实云环境部署、DNS/TLS、受保护发布流水线和 #125 完整跨服务 smoke 仍不在本地联调范围内。 |

因此当前本地联调应按“根级依赖基线 + 服务级 smoke + 手动拼接关键链路”的方式执行。除非 #125 等跨服务 smoke 任务落地，不要在 PR 或文档中声称已有完整一键本地 E2E 验收环境。

## 前置依赖

| 工具 | 当前基线 | 用途 |
| --- | --- | --- |
| Go | `1.25` | 后端服务 build/test/run。 |
| Bun | `bun@1.3.12` | 前端 install/check/build；以根 `packageManager` 为准。 |
| Docker Compose | 支持 Compose v2 | 启动服务级 PostgreSQL、Redis 和服务容器。 |
| PostgreSQL | `postgres:16-alpine` | 服务数据库和 migration smoke。 |
| Redis | `redis:7-alpine` | Gateway session cache、QA/Document 队列。 |
| Alpine runtime | `alpine:3.22` | Go 服务 runtime 和 migration 镜像的运行阶段。 |

Docker 构建优先级按“能跑 > 构建快 > 镜像小 > 内存少 > 存储少”处理。默认
Go Docker build 使用 `GO_DOCKER_GOPROXY=https://proxy.golang.org,direct` 和
`GO_DOCKER_GOSUMDB=sum.golang.org`，保持 checksum verification 开启；国内网络
需要加速时显式设置：

```bash
export GO_DOCKER_GOPROXY=https://goproxy.cn,direct
export GO_DOCKER_GOSUMDB=sum.golang.google.cn
```

不要把 `GOSUMDB=off` 当作普通修复。`goproxy.cn` 的 `sum.golang.org` 代理路径
曾导致 goose migration 镜像构建校验失败；使用 `sum.golang.google.cn` 可以绕开该
第三方 sumdb 代理路径，同时保留模块校验。

Docker daemon mirror、Alpine/Debian/Python 镜像源、BuildKit cache 和磁盘清理见
[`Docker 构建环境与镜像源`](./docker-build-environment.md)。

中国大陆网络的推荐启动路径是显式 registry rewrite，而不是先改 Docker daemon：

```bash
cd deploy
cp .env.example .env
cat .env.china.example >> .env
DOCKER_BUILDKIT=1 docker compose up -d --build
```

已有 daemon mirror 或本机代理时，先跑：

```bash
python3 scripts/check_docker_environment.py --profile all --clean-env
```

如果 `china explicit registry` 通过而 default/daemon mirror 路径失败，继续使用
`.env.china.example`；如果 daemon mirror 全部 manifest 也通过，可以保留本机配置；
如果都失败，再考虑 Docker daemon 级代理。

本地 health/readiness 或 smoke 请求不要走 shell 代理。若当前 shell 设置了
`HTTP_PROXY`/`HTTPS_PROXY`/`http_proxy`/`https_proxy`，先设置
`NO_PROXY=localhost,127.0.0.1,::1`，或在 curl 命令上加 `--noproxy '*'`；否则可能拿到
代理返回的 `503`/超时，而不是本机容器的真实状态。

需要访问 GitHub、Go module proxy、npm registry 或 provider 时，按本机 `proxy` 约定给单条命令加代理环境变量：

```bash
env all_proxy=socks5://127.0.0.1:10808 http_proxy=http://127.0.0.1:10808 https_proxy=http://127.0.0.1:10808 <command>
```

## 根级本地栈

```bash
cd deploy
cp .env.example .env
docker compose up -d --build
```

AI/模型功能所需 AI Gateway profile：

```bash
cd deploy
docker compose --profile ai up -d --build
```

默认根级本地栈可以启动核心服务；管理端模型配置、QA 真实模型调用、Document AI 生成、真实 embedding/rerank 和 provider smoke 需要额外启用该 profile，并检查 `http://localhost:8086/readyz`。本地 seed 的 AI profiles 是 placeholder，不代表真实 provider 已可用。

根级 Compose 详情见 [`deploy/README.md`](../../deploy/README.md)。

## 服务级启动

### File PostgreSQL + MinIO 联合 smoke

仅验证 File 服务自己的 metadata + object storage 组合，不代表完整
Gateway/Knowledge/QA/Document 跨服务 E2E。

先启动 PostgreSQL、MinIO、bucket 初始化和 File migration：

```bash
cd deploy
docker compose --env-file .env.example up -d postgres minio minio-init migrate-file
```

`minio-init` 使用 MinIO `mc` 客户端镜像创建 File Service 本地内部 bucket `software-teamwork-local`；它不是第二个 MinIO server，也不是 owner service 可以依赖的业务 bucket 分类。默认本地配置：

```text
endpoint: localhost:9000
access key: minio_local_demo
secret key: minio-local-demo-password
region: empty
```

然后运行显式启用的 smoke：

```bash
cd ../services/file
FILE_MINIO_POSTGRES_SMOKE=1 \
FILE_TEST_DATABASE_URL='postgres://file_app:file_app_dev@localhost:5432/file_system?sslmode=disable' \
FILE_MINIO_ENDPOINT='localhost:9000' \
FILE_MINIO_ACCESS_KEY='minio_local_demo' \
FILE_MINIO_SECRET_KEY='minio-local-demo-password' \
FILE_MINIO_BUCKET='software-teamwork-local' \
go test ./internal/integration -run TestFileMinIOPostgresSmoke -count=1 -v
```

该测试默认跳过普通 CI。显式启用后会创建独立 PostgreSQL schema，通过
`/internal/v1/files/**` 上传、读取、删除测试对象，并验证删除后 metadata/content
不可读。失败时先看：

```bash
cd ../../deploy
docker compose logs postgres migrate-file minio minio-init
```

### Knowledge ingestion 真实依赖 smoke

仅验证 Knowledge ingestion 主链路，不重复验证 File MinIO smoke、Parser 真实
PaddleOCR 模型 smoke、AI Gateway 真实 provider smoke，也不替代 #125 的 MCP/跨服务
总入口。普通 `go test ./...` 默认跳过该 smoke。

先启动 PostgreSQL、File Service、Parser Service 和 Qdrant。中国大陆网络构建时先把
`deploy/.env.china.example` 追加到本地 `.env`，不要把 `GOSUMDB=off` 当作默认修复：

```bash
cd deploy
cp .env.example .env
# 可选：中国大陆 Docker 构建 overlay
# cat .env.china.example >> .env
DOCKER_BUILDKIT=1 docker compose --env-file .env up -d --build postgres migrate-file file parser qdrant
```

再运行显式启用的 smoke：

```bash
cd ../services/knowledge
KNOWLEDGE_INGESTION_SMOKE=1 \
KNOWLEDGE_TEST_DATABASE_URL='postgres://knowledge_app:knowledge_app_dev@127.0.0.1:5432/knowledge_system?sslmode=disable' \
FILE_SERVICE_BASE_URL='http://127.0.0.1:8082' \
KNOWLEDGE_SERVICE_TOKEN='local-dev-internal-service-token-change-me' \
PARSER_SERVICE_BASE_URL='http://127.0.0.1:8087' \
PARSER_SERVICE_TOKEN='local-dev-internal-service-token-change-me' \
QDRANT_URL='http://127.0.0.1:6333' \
EMBEDDING_PROVIDER=local_hashing \
EMBEDDING_MODEL=local_hashing \
EMBEDDING_DIMENSION=384 \
go test ./internal/integration -run '^TestKnowledgeIngestionRealDepsSmoke$' -count=1 -v
```

该测试会创建独立 PostgreSQL schema `knowledge_smoke_*`，创建 Qdrant collection
`knowledge_ingestion_smoke_*`，上传一个 File Service 对象，直接调用 Knowledge
worker handler 消费捕获到的 ingestion payload，并断言文档 ready、job succeeded、
chunk/embedding metadata 已持久化、Qdrant point payload 可按 chunk id 读取。测试清理会
删除 File 对象、Qdrant collection 和 PostgreSQL schema；如果进程被中断，按这些前缀手动
清理残留。

常见失败先按下面顺序查：

```bash
cd ../../deploy
docker compose ps
docker compose logs postgres migrate-file file parser qdrant
```

排查要点：

- `KNOWLEDGE_INGESTION_SMOKE=1 requires ...`：缺必填 env；失败只列 key，不列值。
- File `401 unauthorized`：确认 `KNOWLEDGE_SERVICE_TOKEN` 等于 Compose 的
  `INTERNAL_SERVICE_TOKEN`。
- Parser dependency error：确认 `PARSER_SERVICE_TOKEN` 和 Parser service token 一致，
  且 Markdown/text fixture 不应触发真实 OCR 模型下载。
- Qdrant `404` 或 collection not found：该 smoke 会创建 run-scoped collection；若仍失败，
  检查 `QDRANT_URL` 是否指向 host 端口 `127.0.0.1:6333`。
- Go module 下载失败：本地临时测试可按 Docker runbook 使用
  `GO_DOCKER_GOPROXY=https://goproxy.cn,direct` 与
  `GO_DOCKER_GOSUMDB=sum.golang.google.cn`，保持 checksum verification 开启。

### Gateway -> Knowledge owner route smoke

该 smoke 只验证 Gateway/Auth/session cache 到 Knowledge owner route 的最小真实链路：
先确认 Parser、File、Knowledge、PostgreSQL 和 Redis ready，再通过 Gateway 创建 session，
然后调用 `GET /api/v1/knowledge-bases`。它不验证上传、Parser 解析质量、Qdrant 检索、
rerank、MCP 或前端流程。

前置发现：如果本机没有 `software-teamwork-local-parser:latest`，下面这类命令会失败：

```bash
docker compose --env-file .env up -d --no-build file parser knowledge
```

原因是 `--no-build` 不能创建缺失的 Parser 镜像；如果改为 build，Parser Dockerfile 又可能
在拉取 `python:3.12-slim` metadata 时被 Docker Hub 超时阻塞。处理顺序：

1. 优先使用 `deploy/.env.china.example` 的显式 registry rewrite / Python package mirror。
2. 预构建或预拉取 Parser 镜像，让 `software-teamwork-local-parser:latest` 进入本机缓存。
3. 再使用 `--no-build` 启动已缓存镜像。

推荐直接启动根级 gateway 依赖基线。Gateway Compose 服务还依赖 QA 和 Document health，
所以只启动 `file parser knowledge gateway` 不一定足够：

```bash
cd deploy
cp .env.example .env
# 可选：中国大陆 Docker 构建 overlay
# cat .env.china.example >> .env
DOCKER_BUILDKIT=1 docker compose --env-file .env build parser
DOCKER_BUILDKIT=1 docker compose --env-file .env up -d --build gateway
```

运行 smoke：

```bash
cd ../services/knowledge
GATEWAY_KNOWLEDGE_OWNER_SMOKE=1 \
GATEWAY_BASE_URL='http://127.0.0.1:8080' \
KNOWLEDGE_SERVICE_BASE_URL='http://127.0.0.1:8083' \
FILE_SERVICE_BASE_URL='http://127.0.0.1:8082' \
PARSER_SERVICE_BASE_URL='http://127.0.0.1:8087' \
KNOWLEDGE_TEST_DATABASE_URL='postgres://knowledge_app:knowledge_app_dev@127.0.0.1:5432/knowledge_system?sslmode=disable' \
KNOWLEDGE_REDIS_ADDR='127.0.0.1:6379' \
GATEWAY_SMOKE_USERNAME='admin' \
GATEWAY_SMOKE_PASSWORD='LocalDemoAdmin#12345' \
go test ./internal/integration -run '^TestGatewayKnowledgeOwnerRouteSmoke$' -count=1 -v
```

该测试会：

- `GET /readyz` 检查 File、Parser 和 Knowledge。
- 使用 `KNOWLEDGE_TEST_DATABASE_URL` ping Knowledge PostgreSQL。
- 使用 `KNOWLEDGE_REDIS_ADDR` 发送 Redis `PING`。
- 调用带伪造 `X-User-*` 但无 Bearer token 的 `GET /api/v1/knowledge-bases`，
  断言 Gateway 返回 `401 unauthorized`。
- `POST /api/v1/sessions` 创建真实 Gateway session。
- 带 Bearer token 调用 `GET /api/v1/knowledge-bases`，同时发送一个伪造的
  `X-User-Id`；Gateway 应忽略该伪造 header 并注入 Auth/session cache 中的上下文。
- 通过 Gateway 创建并读取一个 run-scoped knowledge base，断言 `createdBy` 等于真实
  session user，而不是伪造的 `X-User-Id`。

常见失败：

- `GATEWAY_KNOWLEDGE_OWNER_SMOKE=1 requires ...`：缺必填 env；失败只列 key，不列值。
- `parser readyz request failed` 或 Docker 报缺 `software-teamwork-local-parser:latest`：
  先按上面的 Parser 镜像构建/缓存前置条件处理。
- Gateway session 返回 `401`：确认 `seed-local` 已完成，并使用
  `.env.example` 中的 `admin` / `LocalDemoAdmin#12345` 或显式
  `GATEWAY_SMOKE_USERNAME` / `GATEWAY_SMOKE_PASSWORD`。
- Gateway Knowledge route 返回 `401`：Gateway session cache/Redis 可能不可用；查
  `docker compose logs gateway redis auth`。
- Gateway Knowledge route 返回 `502`：Knowledge owner route 或 service token 配置异常；
  查 `docker compose logs gateway knowledge` 并用相同 `X-Request-Id` 搜索。

### Gateway -> Knowledge -> QA RAG 端到端 smoke

该 smoke 是 Issue #304 的最小 RAG 验收样例。它通过 Gateway public
`/api/v1/**` 创建 session、创建知识库、上传文档、轮询 Knowledge ingestion、
调用 `knowledge-queries`，再配置 QA 的临时 LLM/retrieval config，创建 QA session/message，
并断言 answer 和 citation 摘要。它不替代 #125 的完整跨服务/MCP smoke。

样例固定在测试代码中：

| 项目 | 值 |
| --- | --- |
| 文档文件名 | `gateway-rag-e2e-smoke.md` |
| 样例问题 | `What calibration marker must be checked for the RAG E2E smoke?` |
| 预期命中 | `calibrate relay RAG-E2E-304` |
| 预期 citation 字段 | `knowledgeBaseId`、`documentId`、`chunkId` 非空且匹配本轮资源；`contentPreview` 或 `text` 包含预期命中。 |

前置要求：

- 根级 Compose 需要带 `--profile ai` 启动，使 AI Gateway、migration 和 placeholder
  profile seed 可用。
- `QA_SETTINGS_OPEN=true` 只建议在本地 smoke 环境启用，用于允许测试通过 Gateway
  创建本轮 QA/LLM config versions。也可改用符合
  [QA 权限矩阵](../services/qa/docs/permission-matrix.md) 的管理账号或
  `QA_ADMIN_USER_IDS` 的账号。
- `QA_SMOKE_CHAT_PROFILE_ID` 和 `QA_SMOKE_CHAT_MODEL` 必须指向 AI Gateway 中可实际
  调用的 chat profile/model。`.env.example` 的 `default-chat` /
  `local-placeholder-chat` 只在 `host.docker.internal:11434/v1` 后面有可用
  OpenAI-compatible provider 时可用；真实 provider 或受控 stub provider 仍需显式配置。
- 默认 Knowledge 使用 local hashing embedding 和 in-memory vector index。需要证明
  Qdrant runtime 查询时，在启动前设置 `KNOWLEDGE_QDRANT_URL=http://qdrant:6333`。
  需要真实 AI Gateway embedding/rerank 时，再设置 `EMBEDDING_PROVIDER=ai_gateway`、
  `KNOWLEDGE_AI_GATEWAY_BASE_URL=http://ai-gateway:8086`、embedding profile/model
  和 `RERANK_MODEL` / `RERANK_PROFILE_ID`。

启动本地栈：

```bash
cd deploy
cp .env.example .env
# 可选：中国大陆 Docker 构建 overlay
# cat .env.china.example >> .env
QA_SETTINGS_OPEN=true DOCKER_BUILDKIT=1 docker compose --env-file .env --profile ai up -d --build gateway ai-gateway
```

运行 smoke：

```bash
cd ../services/knowledge
GATEWAY_RAG_E2E_SMOKE=1 \
GATEWAY_BASE_URL='http://127.0.0.1:8080' \
FILE_SERVICE_BASE_URL='http://127.0.0.1:8082' \
PARSER_SERVICE_BASE_URL='http://127.0.0.1:8087' \
KNOWLEDGE_SERVICE_BASE_URL='http://127.0.0.1:8083' \
QA_SERVICE_BASE_URL='http://127.0.0.1:8084' \
AI_GATEWAY_BASE_URL='http://127.0.0.1:8086' \
KNOWLEDGE_TEST_DATABASE_URL='postgres://knowledge_app:knowledge_app_dev@127.0.0.1:5432/knowledge_system?sslmode=disable' \
KNOWLEDGE_REDIS_ADDR='127.0.0.1:6379' \
GATEWAY_SMOKE_USERNAME='admin' \
GATEWAY_SMOKE_PASSWORD='LocalDemoAdmin#12345' \
QA_SMOKE_CHAT_PROFILE_ID='default-chat' \
QA_SMOKE_CHAT_MODEL='local-placeholder-chat' \
go test ./internal/integration -run '^TestGatewayRAGE2ESmoke$' -count=1 -v
```

预期结果：

```text
=== RUN   TestGatewayRAGE2ESmoke
--- PASS: TestGatewayRAGE2ESmoke (...s)
PASS
```

测试会创建 run-scoped knowledge base 和文档，并在清理阶段先调用 Gateway
`DELETE /api/v1/documents/{documentId}` 触发 File/vector cleanup，再按
chunks、jobs、documents、knowledge base 的顺序删除本轮 Knowledge PostgreSQL 行。
测试开始前会读取当前 active QA config 和 LLM config，结束时通过 Gateway settings API
重新创建并激活一份等价恢复版本。本轮 smoke 创建的 QA config versions 仍会作为本地运行
记录留存，因为它们是 QA settings 的真实业务资源；只在临时本地栈运行该 smoke。

常见失败和定位：

| 阶段 | 典型失败 | 排查 |
| --- | --- | --- |
| File | `File stage: gateway document upload returned HTTP ...` | 查 `docker compose logs gateway file`，确认 File ready、`INTERNAL_SERVICE_TOKEN` 一致、上传大小未超限。不要打印 multipart body 或 object key。 |
| Parser | `Parser stage: ready document did not record parserBackend` 或文档状态 `failed` | 查 `docker compose logs knowledge parser`，确认 Parser ready、`PARSER_SERVICE_TOKEN` 一致；Markdown fixture 不需要真实 OCR 模型下载。 |
| Knowledge ingestion | `document ... did not become ready` 或 `chunkCount = 0` | 查 `docker compose logs knowledge redis postgres qdrant`；检查 `processing_jobs` 状态、Redis/asynq 投递和 Qdrant/local vector 配置。 |
| Knowledge retrieval | `Knowledge retrieval stage: ...`、无 expected hit 或 rerank trace 异常 | 查 `docker compose logs gateway knowledge ai-gateway qdrant`；确认 `knowledge-queries` 返回 ready 文档 chunk，`rerank=true` 在无 `RERANK_MODEL` 时只证明 no-op fallback trace。 |
| AI Gateway | QA message 返回 `502`、model error 或 provider unavailable | 查 `docker compose logs qa ai-gateway`；确认 chat profile enabled、model exact-match、credential/provider 可用。不要粘贴 provider 原始错误 body 或 API key。 |
| QA | QA config POST `403/400`、answer 未完成、无 citation | 确认 `QA_SETTINGS_OPEN=true` 或账号满足 [QA 权限矩阵](../services/qa/docs/permission-matrix.md) 的配置写入要求；确认模型支持 OpenAI-compatible tool/function calling，并且 QA config 只启用 `search_knowledge`。 |

如果只需要验证 Knowledge ingestion 和 retrieval，不要运行本 RAG smoke；先使用上面的
`KNOWLEDGE_INGESTION_SMOKE` 或 `GATEWAY_KNOWLEDGE_OWNER_SMOKE` 缩小范围。

### QA + Auth + Gateway 局部环境

```bash
cd services/qa
docker compose up --build
```

该 Compose 适合验证 Auth、QA、Gateway 的基础 ready 状态和 QA 非 provider 依赖路径：

```bash
curl -fsS http://localhost:8081/readyz
curl -fsS http://localhost:8084/readyz
curl -fsS http://localhost:8080/readyz
```

注意：默认 `AI_GATEWAY_URL` 指向 Compose 网络内的 `http://ai-gateway:8086/internal/v1/chat/completions`，但该 Compose 没有 `ai-gateway` 服务。触发真实 LLM 调用、LLM connection test 或 Agent Run 时，需要额外启动 AI Gateway 并改写 `QA_AI_GATEWAY_URL`。

### Document 局部环境

```bash
cd services/document
docker compose up --build
```

该 Compose 适合验证 Document PostgreSQL、Redis、migration、job enqueue 和 worker 状态机：

```bash
curl -fsS http://localhost:8085/readyz
```

注意：模板、材料和报告文件 bytes 需要 File Service；真实大纲/正文生成需要 AI Gateway。当前基础 DOCX 导出使用 Document 内置 `SimpleDOCXGenerator`，不需要 Pandoc/LibreOffice；Pandoc/LibreOffice 仅是后续富 DOCX worker 工具链。当前 Compose 只给 File/AI Gateway 下游设置 URL，不启动这些下游服务，所以 Document-only 环境不能完整读取生成文件内容。Document worker 会执行 `report_file_creation` 的基础 DOCX 导出；其他大纲/正文生成类 job 仍只完成 job/attempt 状态流转。

### AI Gateway root profile / host-run

根级 `deploy/docker-compose.yml` 的 `--profile ai` 会启动 AI Gateway、执行 migration，并通过
`seed-local-ai` 写入本地 placeholder profile。下面的 host-run 示例用于单独调试服务进程。
AI Gateway 服务 token 运行时只接受 hash：

```bash
TOKEN=dev-internal-service-token-change-me
printf '%s' "$TOKEN" | shasum -a 256 | awk '{print "sha256:" $1}'
```

最小 host-run 环境示例：

```bash
export AI_GATEWAY_HTTP_ADDR=:8086
export AI_GATEWAY_DATABASE_URL='postgres://ai_gateway:ai_gateway@localhost:5436/ai_gateway?sslmode=disable'
export AI_GATEWAY_SERVICE_TOKEN_HASHES='sha256:<token-sha256-hex>'
export AI_GATEWAY_CREDENTIAL_ENCRYPTION_KEY_REF=local-dev-key-v1
export AI_GATEWAY_CREDENTIAL_ENCRYPTION_KEY='<long-local-secret>'

cd services/ai-gateway
go run github.com/pressly/goose/v3/cmd/goose@v3.27.1 -dir migrations postgres "$AI_GATEWAY_DATABASE_URL" up
go run ./cmd/server
```

创建可调用 profile 后，`/internal/v1/chat/completions`、`/internal/v1/embeddings` 和 `/internal/v1/rerankings` 都会按 profile 解析 provider、model、base URL 和 API key。当前 fake-provider 单元测试覆盖了协议形态；真实 provider smoke 仍需单独执行并记录。

## 手动联调顺序

完整链路尚未一键化时，建议按下面顺序缩小问题范围：

1. 单服务测试和 build 先通过：`go test ./...`、`go build ./cmd/server`。
2. 对有 migration 的服务执行 goose apply smoke。
3. 启动 Auth、Gateway、目标领域服务和该领域服务的数据库。
4. 需要模型调用时再启动 AI Gateway，并创建对应 `purpose=chat|embedding|rerank` 的 enabled/default profile。
5. 需要文件 bytes 时再启动 File Service；不要让领域服务直接暴露 object key、bucket 或内部 URL。
6. 通过 Gateway public `/api/v1/**` 验证前端可见能力；只在服务间 smoke 中直连 `/internal/v1/**`。

## 冒烟检查清单

| 场景 | 检查 | 当前预期 |
| --- | --- | --- |
| Auth/Gateway/QA 局部环境 | `GET /readyz` | 三个服务 ready；真实 AI 调用可能因未启动 AI Gateway 失败。 |
| Document 局部环境 | 创建 report job 后查询 job/attempt/events | 非文件生成类任务会入队并由 worker 推进为 succeeded；不会生成真实 AI 大纲/正文。若额外提供 File Service，`report_file_creation` 可生成基础 DOCX 并通过 content endpoint 读取成功文件。 |
| AI Gateway profile | 创建 chat/embedding/rerank profile，调用对应内部 endpoint | fake provider 和兼容 provider 应返回 OpenAI-style body；真实 provider 需手工验证。 |
| Gateway contract | `python3 scripts/verify_gateway_active_api.py` | active path、owner、security 和 owner map 不漂移。 |
| Parser PaddleOCR model | `PARSER_PADDLEOCR_SMOKE=1 PARSER_PADDLEOCR_ALLOW_DOWNLOAD=1 uv run pytest -m paddleocr_smoke -s` | 只在本机具备 PaddleOCR extra 和可用模型下载/缓存时运行；验证真实模型加载和最小 fixture OCR 非空。 |
| File PostgreSQL + MinIO | `FILE_MINIO_POSTGRES_SMOKE=1 ... go test ./internal/integration -run TestFileMinIOPostgresSmoke -count=1 -v` | 只在真实 PostgreSQL/MinIO 可用时运行；验证 upload、metadata、content read、delete 和清理状态。 |
| Knowledge ingestion real deps | `KNOWLEDGE_INGESTION_SMOKE=1 ... go test ./internal/integration -run '^TestKnowledgeIngestionRealDepsSmoke$' -count=1 -v` | 只在 PostgreSQL/File/Parser/Qdrant 可用时运行；验证 fixture 上传、解析、切片、embedding、Qdrant point 写入和状态更新。 |
| Gateway -> Knowledge owner route | `GATEWAY_KNOWLEDGE_OWNER_SMOKE=1 ... go test ./internal/integration -run '^TestGatewayKnowledgeOwnerRouteSmoke$' -count=1 -v` | 只在 Gateway/Auth/Redis/Knowledge/File/Parser/PostgreSQL 可用时运行；验证伪造 `X-User-*` 未认证请求被拒绝，并用 KB `createdBy` 断言 Gateway 注入真实 session user。 |
| Gateway -> Knowledge -> QA RAG | `GATEWAY_RAG_E2E_SMOKE=1 ... go test ./internal/integration -run '^TestGatewayRAGE2ESmoke$' -count=1 -v` | 只在 Gateway/Auth/Redis/File/Parser/Knowledge/QA/AI Gateway 和可用 chat profile/provider 可用时运行；验证上传、ingestion ready、`knowledge-queries` 命中、QA answer 和 citation 摘要。 |
| 前端 Gateway 类型 | `bun run --cwd apps/web api:generate` 后检查 diff | 生成类型应与 Gateway OpenAPI 保持同步。 |

## 已知缺口

| 缺口 | 影响 | 跟踪 |
| --- | --- | --- |
| 根级跨服务 smoke 缺失 | 即使使用 `deploy/docker-compose.yml` 启动本地/演示基线，也不能自动证明 Auth/Gateway/File/Knowledge/QA/Document/AI Gateway 链路可用。 | #125 |
| 跨服务契约测试和 E2E smoke 缺失 | 不能自动证明前端 -> Gateway -> 多服务链路可用。 | #125 |
| Parser 真实 OCR smoke 不在普通 CI 中运行 | Parser 已有 env-gated 真实 PaddleOCR 模型 smoke，但 CI 仍使用 fake OCR backend；真实模型、OCR 质量和部署资源需要在具备模型的本地或部署环境手动记录。 | #125 |
| Knowledge/QA RAG smoke 仍为显式 opt-in | File 自身 PostgreSQL + MinIO smoke 已有；Knowledge ingestion 真实依赖 smoke 已覆盖 File/Parser/PostgreSQL/Qdrant 写入和状态更新；Gateway -> Knowledge -> QA RAG smoke 已提供最小验收样例，但依赖可用 AI Gateway chat profile/provider，且不覆盖 MCP、前端或 #125 完整一键 E2E。 | #125、#152、#154、#304 |
| 生产部署基线缺失 | 当前 `deploy/docker-compose.yml` 是本地/演示基线，不能直接当生产部署。 | #150 |
| Document 真实 AI 生成和富 DOCX 工具链未落地 | 报告 job 状态机和基础 DOCX 导出可用；真实大纲/正文生成、Pandoc/LibreOffice 富 DOCX 转换和跨服务内容读取 smoke 仍需补齐。 | #160、#223 |
| Document 跨服务 smoke 仍缺失 | settings/statistics/logs 已在服务端落地，但管理端、Gateway、File Service、Document worker 串联 smoke 仍未一键化。 | #159、#221 |
| QA Agent Run MVP 和权限一致性仍在推进 | QA 会话/消息基础可用，完整 Agent 编排和 403 一致性仍需收口。 | #157、#217 |
| 前端业务 E2E 覆盖不足 | 已有 Playwright 基础 smoke；Knowledge、QA、Document 等完整业务流程仍需随页面能力扩展。 | #117、#163 |

## PR 前判断

- 只改文档：至少执行 `git diff --check`，并检查新增链接、相对路径和实现事实。
- 改后端服务：执行对应服务 `go test ./...` 和 `go build ./cmd/server`；QA 还要 `go build ./cmd/agent`。
- 改 migration：执行 goose apply；如果服务有 env-gated repository integration tests，尽量使用本地 PostgreSQL 跑一遍。
- 改 Parser 契约或运行时：检查 `docs/services/parser/api/internal.openapi.yaml`、`services/parser/api/openapi.yaml`（实现本地副本）、Parser README、Knowledge ingestion 文档和 `parser-service.yml` 是否一致；运行 `cd services/parser && uv run ruff check . && uv run pytest && uv run python -m compileall src tests`。如触碰 PaddleOCR runtime 或部署资源，尽量追加 `PARSER_PADDLEOCR_SMOKE=1` 的真实模型 smoke，并在 PR 记录中区分 fake OCR 与真实模型结果。
- 改 Gateway OpenAPI：执行 `python3 scripts/verify_gateway_active_api.py`，前端类型相关改动还要执行 `bun run --cwd apps/web api:generate` 并检查生成 diff。
- 改前端：执行 `bun install --frozen-lockfile`、`bun run --cwd apps/web check`、`bun run --cwd apps/web build`、`bun run --cwd apps/web test:unit`；关键页面改动再跑 `bun run --cwd apps/web test:e2e`。

## Appendix: AI Gateway real-provider cross-service acceptance

Use this checklist only in a protected local or shared environment that can hold
real provider credentials. Do not commit `.env` values, provider keys, service
tokens, full prompts, document text, embedding payloads, or provider raw error
bodies.

1. Start the local AI profile stack:
   `cd deploy && docker compose --profile ai up -d --build`.
2. Check AI Gateway readiness:
   `curl -s http://127.0.0.1:8086/readyz`.
   `missing` means the profile or active credential is absent; `placeholder`
   means the seeded local fake credential is still present; `ok` means a
   non-placeholder credential is configured, not that the external provider has
   accepted it.
3. Create or patch chat, embedding, and rerank profiles through
   `/internal/v1/model-profiles` with `X-Service-Token`,
   `X-Caller-Service`, and `X-Request-Id`. The `model` in smoke requests must
   exactly match the selected profile.
4. Run direct AI Gateway smoke with
   `AI_GATEWAY_REAL_PROVIDER_SMOKE=1`. Chat is the minimum; embedding and rerank
   run only when the provider and env vars support them.
5. Run QA validation by creating a Gateway session, creating a QA session, and
   sending a message through Gateway public `/api/v1/**` or the documented
   `QA_AI_GATEWAY_SMOKE=1` service-client test. Use the same request id to
   search `docker compose logs gateway qa ai-gateway`.
6. Run Document validation for `summer_peak_inspection`: create a report,
   create an `outline_generation` or `content_generation` job, poll jobs,
   events, and sections until terminal state, then search
   `docker compose logs gateway document ai-gateway` by request id. Rich DOCX
   Pandoc/LibreOffice worker validation is not part of this checklist.
7. Run Knowledge validation in the intended mode. The default local path uses
   local hashing embeddings and no-op/empty rerank configuration; do not count
   it as real AI Gateway embedding/rerank. For real provider validation set
   `EMBEDDING_PROVIDER=ai_gateway`,
   `KNOWLEDGE_AI_GATEWAY_BASE_URL=http://ai-gateway:8086`, and the embedding or
   rerank profile/model env vars, then inspect Knowledge and AI Gateway logs by
   request id.

Acceptance record template:

| Area | Command or request | Expected proof | Logs |
| --- | --- | --- | --- |
| AI Gateway | `/readyz` + real provider smoke | profile status is not `placeholder`; smoke succeeds for configured operations | `docker compose logs ai-gateway` |
| QA | session/message or `QA_AI_GATEWAY_SMOKE=1` | answer path reaches AI Gateway and returns normalized response/error | `docker compose logs gateway qa ai-gateway` |
| Knowledge | local hashing or AI Gateway embedding/rerank path | selected path is explicitly named; real provider path has profile/model env | `docker compose logs gateway knowledge ai-gateway qdrant` |
| Document | `summer_peak_inspection` report job flow | job/events/sections reach expected terminal state | `docker compose logs gateway document ai-gateway redis` |
