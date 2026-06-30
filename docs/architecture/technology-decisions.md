# 技术选型基线

本文记录当前团队确认的工程技术选型、版本固定状态和落地约束。后续服务实现、接口文档、CI 和部署文档应以本文为基线；如需偏离，必须在对应服务 README 说明原因并同步更新本文。

## 总体原则

- 后端服务继续采用独立 Go module 的微服务形态。
- 前端继续采用 `apps/web` 下的 Bun + Vite + React + TypeScript 应用。
- 服务间通信以 RESTful HTTP API 为主，公开接口以 gateway OpenAPI 为权威。
- 技术选型优先选择团队可维护、容易在 CI 中验证、和当前代码形态一致的方案。
- 已经写入 `package.json`、`bun.lock`、`go.mod`、Dockerfile、Compose 或 GitHub Actions 的版本视为当前仓库版本。
- 本地开发 Compose 中仍有 `latest` 镜像 tag；这些只代表当前未固定版本状态，不允许直接作为生产部署基线。

## 版本标注规则

| 标注 | 含义 |
| --- | --- |
| 已固定 | 版本已经在仓库配置或锁文件中固定，新代码默认沿用该版本或同一大版本。 |
| 已选型，待固定 | 技术路线已确认，但仓库尚未引入依赖、CLI 或镜像版本；首次落地时必须写入明确版本并更新本文。 |
| 标准库 / 协议 | 由 Go 标准库、Web 标准、HTTP/OpenAPI 协议或团队契约定义，不存在独立第三方依赖版本。 |
| 当前为 `latest` | 本地 Compose 已使用 `latest` tag，但还没有可复现版本；生产前必须改成明确 tag。 |

## 服务文档使用方式

本文是项目技术选型的权威位置。`docs/services/<service>/README.md` 不应复制完整技术栈表；服务文档只记录：

- 本服务是否适用某项通用选型，例如是否拥有 PostgreSQL、Redis/asynq、MinIO、Qdrant 或模型调用。
- 本服务的服务内目录、迁移、任务、日志字段或测试重点。
- 与本文不同的明确偏离原因；偏离必须同时更新本文和对应服务文档。

如果只是说明 `pgx` + `sqlc`、`goose`、`net/http` / `ServeMux`、`slog`、`envconfig` 风格配置、统一测试工具或前端 OpenAPI 类型生成，应在服务文档中链接本文，不重复描述。

## 当前仓库状态

| 模块 | 当前状态 | 版本来源 |
| --- | --- | --- |
| `apps/web` | 已落地前端应用，使用 Bun workspace、Vite、React、TypeScript、Tailwind 和 ESLint Flat Config。 | 根 `package.json`、`apps/web/package.json`、`bun.lock` |
| `services/gateway` | 已落地 Go gateway、auth public routes、Redis session cache、active proxy route matrix 和边缘中间件；部分 active Knowledge routes 仍返回 `not_implemented`。 | `services/gateway/go.mod`、`services/gateway/internal/http/routes.go`、`docs/services/gateway/docs/implementation.md` |
| `services/auth` | 已落地 Go auth 服务、PostgreSQL repository、用户/会话内部 API、argon2id、token hash 和 migration。 | `services/auth/go.mod`、`services/auth/migrations/`、`docs/services/auth/docs/implementation.md` |
| `services/file` | 已落地 Go file 服务、基础 `/internal/v1/files/**` API、memory/local/MinIO object store、file_objects migration、PostgreSQL metadata runtime 和 service-token 校验；`FILE_DATABASE_URL` 为空时仍保留 memory metadata 模式。 | `services/file/go.mod`、`services/file/migrations/`、`docs/services/file/docs/implementation.md` |
| `services/knowledge` | 已落地 Go knowledge 服务、PostgreSQL repository、知识库 CRUD、文档上传 handoff 和 asynq 入队；入库 worker、Qdrant、embedding、retrieval 尚未落地。 | `services/knowledge/go.mod`、`services/knowledge/migrations/`、`docs/services/knowledge/docs/implementation.md` |
| `services/parser` | 已新增 parser runtime 契约和目录 scaffold，目标运行时为 Python + PaddleOCR；尚未添加 Python/PaddleOCR 依赖、Docker image 或部署 wiring。 | `services/parser/README.md`、`docs/services/parser/README.md`、`docs/services/parser/api/public.openapi.yaml`、`docs/services/parser/api/internal.openapi.yaml` |
| `services/qa` | 已落地 Go QA 服务、PostgreSQL repository、会话/消息/SSE、配置、引用、工具/MCP/model client 基础；默认走 AI Gateway chat，真实 Knowledge retrieval 和跨服务 smoke 仍待补齐。 | `services/qa/go.mod`、`services/qa/migrations/`、`docs/services/qa/docs/implementation.md` |
| `services/document` | 已落地 Go document 服务、PostgreSQL repository、模板/材料/报告/大纲/章节 API、report jobs/attempts/events 和 asynq worker 状态机；report files、statistics、settings 和真实 AI/Pandoc/DOCX 生成仍未落地。 | `services/document/go.mod`、`services/document/migrations/`、`docs/services/document/docs/implementation.md` |
| `services/ai-gateway` | 已落地 Go AI Gateway、PostgreSQL repository、model profile CRUD、credential encryption、service-token auth、OpenAI-compatible chat completions、embeddings、rerankings、provider invocation 记录和 usage aggregate；真实 provider/跨服务 smoke 仍待补齐。 | `services/ai-gateway/go.mod`、`services/ai-gateway/migrations/`、`docs/services/ai-gateway/docs/implementation.md` |
| CI | 已有 PR guard、commitlint、auto-label、Go service build/test workflow 和 goose migration apply workflow；前端流水线尚未落地。 | `.github/workflows/*.yml` |

## 当前事实与目标基线

本文同时记录当前仓库事实和目标技术基线。已经写入仓库配置或锁文件的版本先按当前事实记录；如果与目标基线不一致，应优先开实现 issue 让代码向目标基线对齐，而不是在实现 PR 中临时改契约或让文档长期迁就漂移。

当前已知需要对齐的差异：

| 领域 | 当前仓库事实 | 目标基线 / 后续动作 |
| --- | --- | --- |
| PostgreSQL client | Auth 仍使用 `pgx/v4@v4.18.3`；File、Knowledge、QA、Document、AI Gateway 使用 `pgx/v5@v5.7.6`。 | 目标基线统一为 `pgx/v5@v5.7.6`；新增服务不得引入 `pgx/v4`，Auth 需迁移到 v5。 |
| Redis client | Gateway 直接使用 `go-redis/v9@v9.21.0`；Knowledge 通过 asynq 间接使用 `go-redis/v9@v9.14.1`。 | 后续统一 Redis client 版本策略，并同步 `go.mod` 和本文。 |
| asynq | Knowledge 和 Document 已接入 `asynq v0.26.0`；队列目标基线已确认。 | 技术表和三选一记录统一标为已固定；新增异步任务复用该版本或显式决策升级。 |
| File object store | Runtime 已有 memory/local/MinIO object store；MinIO server/mc 本地初始化尚未落地。 | File 仍是 MinIO 对象存储边界；SDK 已固定，server/client 镜像版本在 Compose 或部署落地时固定。 |
| 前端 OpenAPI 类型生成 | `openapi-typescript@7.13.0` 已进入 `apps/web/package.json` 和 `bun.lock`。 | API type drift check 持续约束 generated diff；升级版本需同步本文。 |

## 已确认选型总览

| 领域 | 选型 | 当前版本 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| Monorepo 包管理 | Bun workspace | `bun@1.3.12` | 已固定 | 根目录 `packageManager` 固定；`bun.lock` 为唯一前端锁文件。 |
| 前端框架 | React + React DOM | `19.2.7` | 已固定 | `apps/web` 使用 React 19。 |
| 前端语言 | TypeScript | `6.0.3` lock，`~6.0.2` range | 已固定 | 以 `bun.lock` 解析版本为准。 |
| 前端构建 | Vite | `8.1.0` | 已固定 | 使用 `@vitejs/plugin-react` 和 `@tailwindcss/vite`。 |
| 前端样式 | Tailwind CSS | `4.3.1` | 已固定 | 配套 `@tailwindcss/vite@4.3.1`。 |
| 前端路由 | TanStack Router | `@tanstack/react-router@1.170.16` | 已固定 | `apps/web/src/app/router.tsx` 负责路由组合。 |
| 前端服务状态 | TanStack Query | `@tanstack/react-query@5.101.1` | 已固定 | 用于服务端状态、缓存和 mutation。 |
| 前端客户端状态 | Zustand | `5.0.14` | 已固定 | 用于主题、认证、UI、聊天等本地状态。 |
| 前端运行时校验 | Zod | `4.4.3` | 已固定 | 用于 schema 与输入校验。 |
| 前端 UI 基础 | Base UI + Radix primitives | Base UI `1.6.0`；Radix 见前端明细 | 已固定 | `components.json` 使用 `base-nova`、Lucide icons、Tailwind CSS variables。 |
| 前端图标 | Lucide React | `1.21.0` | 已固定 | `components.json` 的 `iconLibrary` 为 `lucide`。 |
| 前端 Markdown | react-markdown | `10.1.0` | 已固定 | QA 聊天消息渲染使用。 |
| 前端 class 工具 | `clsx` + `class-variance-authority` | `clsx@2.1.1`，`cva@0.7.1` | 已固定 | UI variant 和 class 合并基础。 |
| 前端 API 类型 | `openapi-typescript` + typed fetch wrapper | `openapi-typescript@7.13.0` | 已固定 | `api:generate` 已进入 `apps/web/package.json`；生成目录为 `apps/web/src/api/generated/`。 |
| 前端 SSE | `fetch` stream wrapper | Web 标准 | 标准库 / 协议 | QA 消息创建使用 POST + `text/event-stream`，支持 `AbortController`。 |
| 前端测试 | Vitest + React Testing Library + Playwright | 待固定 | 已选型，待固定 | 当前未加入 `apps/web/package.json`。 |
| 前端代码质量 | ESLint Flat Config + Prettier | ESLint `9.39.4`，Prettier `3.9.0` | 已固定 | 插件版本见前端明细。 |
| 后端语言 | Go | `go 1.25` | 已固定 | 项目 Go 服务基线固定为 1.25；已落地服务 module 和 Dockerfile 应保持一致。 |
| 后端 HTTP 路由 | Go `net/http` / `http.ServeMux` | Go `1.25` 标准库 | 已固定 | 不默认引入 `gin`/`chi`。 |
| 后端日志 | Go `log/slog` | Go `1.25` 标准库 | 已固定 | 生产默认 JSON 结构化日志。 |
| PostgreSQL 访问 | `pgx` + `sqlc` | `pgx/v4@v4.18.3`、`pgx/v5@v5.7.6`；sqlc 生成版本按服务记录 | 部分已固定 | Auth 仍用 `pgx/v4`；Knowledge、QA、Document、AI Gateway 用 `pgx/v5`，新增和迁移后的服务默认使用 `pgx/v5`。Knowledge/QA 生成包为 `sqlc v1.29.0`，Auth/Document 生成包为 `sqlc v1.31.1`；后续按任务统一生成策略。 |
| ORM | 不使用 ORM | N/A | 已固定 | 禁止默认引入 GORM/ent 等 ORM。 |
| 数据库迁移 | `goose` | `v3.27.1` | 已固定 | 使用 `pressly/goose` CLI 或库执行服务内 migration；该版本要求 Go 1.25+。 |
| 关系数据库 | PostgreSQL | `postgres:16-alpine` | 已固定 | 当前本地 Compose 固定在 16 Alpine。 |
| Redis 队列 | `asynq` over Redis | `asynq v0.26.0`；Redis `7-alpine` | 已固定 | Knowledge 和 Document 已接入 asynq client/worker；后续异步服务按需复用该队列基线。 |
| Redis 缓存/会话 | `go-redis` | `go-redis/v9 v9.21.0`、`v9.14.1` 间接依赖 | 部分已固定 | Gateway 直接使用 `github.com/redis/go-redis/v9@v9.21.0`；Knowledge 通过 asynq 间接固定 `v9.14.1`。后续需统一版本策略。 |
| 向量数据库 | Qdrant | 镜像版本待固定 | 已选型，待固定 | Knowledge schema 已保留 Qdrant point 字段；runtime adapter 尚未落地。 |
| Qdrant 客户端 | 手写 HTTP client | Go 标准 HTTP client | 已选型，待落地 | 当前代码尚未实现 Qdrant client；落地时先不引入官方 client。 |
| 对象存储 | MinIO 边界；当前 memory/local/MinIO object store | MinIO 镜像版本待固定 | 部分已固定 | File service runtime 已有 MinIO adapter；MinIO server/mc 镜像版本待本地 Compose 或部署落地时固定。 |
| MinIO Go SDK | 官方 MinIO Go SDK | `github.com/minio/minio-go/v7@v7.2.1` | 已固定 | `services/file` 通过 `internal/platform/storage` 封装 SDK，不向 handler 或 owner service client 泄露 MinIO 细节。 |
| 认证 token | Opaque Bearer token | 协议契约 | 标准库 / 协议 | 不使用 JWT access token；服务端保存 token hash。 |
| 密码哈希 | `argon2id` | `argon2id-v1`，PHC `v=19` | 已固定 | 参数：`m=65536 KiB`、`t=3`、`p=2`、`salt=16 bytes`、`key=32 bytes`。 |
| Secret 管理 | 本地 env；生产 secret ref；第一阶段可加密列 | 加密实现待固定 | 已选型，待固定 | AI Gateway 不保存明文 provider API key。 |
| 模型调用 | AI Gateway 统一封装 OpenAI-compatible API | API 契约 `0.1.0`；provider/model 运行时配置 | 部分已落地 | chat completions、function calling 透传、embeddings 和 rerankings 已落地；真实 provider smoke 和下游接入仍待补齐。 |
| 本地 embedding | local hashing embedding | 待实现 | 已选型，待落地 | AI Gateway embedding endpoint 已支持 OpenAI-compatible provider；local hashing embedding provider adapter 尚未落地。 |
| 文档解析运行时 | Python + PaddleOCR behind Parser HTTP API | 待固定 | 已选型，待落地 | Parser 通过 `/internal/v1/parsed-documents` 提供解析结果；Knowledge 不承载 PaddleOCR/PaddlePaddle/OpenCV/CUDA 依赖。 |
| OpenAPI | OpenAPI | `3.0.3` | 已固定 | Gateway、Auth、Knowledge、QA、Document、AI Gateway 契约均使用 3.0.3。 |
| API 版本前缀 | `/api/v1` / `/internal/v1` | `v1` | 已固定 | 公开入口以 gateway OpenAPI 为准；内部服务使用服务级契约。 |
| 后端测试 | Go `testing` + `httptest` | Go `1.25` 标准库 | 已固定 | 默认不引入 BDD 测试框架。 |
| CI | GitHub Actions | `actions/github-script@v7`；runner `ubuntu-latest` | 部分已固定 | 已有协作类 workflow、Go service build/test workflow 和 goose migration apply workflow；前端 workflow 尚待落地。 |
| 观测 | `slog` + Prometheus metrics；关键链路 OpenTelemetry tracing | Prometheus/OTel 依赖待固定 | 已选型，待固定 | 第一阶段先保证结构化日志和指标。 |
| DOCX 生成 | Document worker 调用 Pandoc/LibreOffice 类工具链 | 待固定 | 已选型，待固定 | 落地时必须固定工具链镜像或 CLI 版本。 |
| MCP 集成 | 成熟 SDK 或独立 MCP sidecar | 待固定 | 已选型，待固定 | QA 负责工具白名单、权限、参数校验和脱敏记录。 |
| 本地部署 | Docker Compose | Compose 文件格式无 top-level version | 已选型 | QA 和 Document 已有服务本地 Compose；根 `deploy/docker-compose.yml` 尚未落地。 |

## 前端版本明细

| 类型 | 包 | 当前版本 |
| --- | --- | --- |
| Runtime | `react` | `19.2.7` |
| Runtime | `react-dom` | `19.2.7` |
| Runtime | `@tanstack/react-query` | `5.101.1` |
| Runtime | `@tanstack/react-router` | `1.170.16` |
| Runtime | `zustand` | `5.0.14` |
| Runtime | `zod` | `4.4.3` |
| Runtime | `react-markdown` | `10.1.0` |
| UI | `@base-ui/react` | `1.6.0` |
| UI | `@radix-ui/react-collapsible` | `1.1.14` |
| UI | `@radix-ui/react-dialog` | `1.1.17` |
| UI | `@radix-ui/react-hover-card` | `1.1.17` |
| UI | `@radix-ui/react-popover` | `1.1.17` |
| UI | `@radix-ui/react-scroll-area` | `1.2.12` |
| UI | `@radix-ui/react-slot` | `1.3.0` |
| UI | `lucide-react` | `1.21.0` |
| UI | `class-variance-authority` | `0.7.1` |
| UI | `clsx` | `2.1.1` |
| Style / Build | `tailwindcss` | `4.3.1` |
| Style / Build | `@tailwindcss/vite` | `4.3.1` |
| Build | `vite` | `8.1.0` |
| Build | `@vitejs/plugin-react` | `6.0.3` |
| Language | `typescript` | `6.0.3` |
| Types | `@types/node` | `26.0.1` |
| Types | `@types/react` | `19.2.17` |
| Types | `@types/react-dom` | `19.2.3` |
| Lint | `eslint` | `9.39.4` |
| Lint | `@eslint/js` | `9.39.4` |
| Lint | `typescript-eslint` | `8.62.0` |
| Lint | `eslint-config-prettier` | `10.1.8` |
| Lint | `eslint-plugin-jsx-a11y` | `6.10.2` |
| Lint | `eslint-plugin-react` | `7.37.5` |
| Lint | `eslint-plugin-react-hooks` | `7.1.1` |
| Lint | `eslint-plugin-simple-import-sort` | `13.0.0` |
| Format | `prettier` | `3.9.0` |

## 后端与基础设施版本明细

| 组件 | 当前版本 | 来源 | 备注 |
| --- | --- | --- | --- |
| Go toolchain | `1.25` | 技术选型基线 | Go 服务统一使用 1.25；`services/*/go.mod` 和 Go build Dockerfile 应保持一致。 |
| `github.com/jackc/pgx/v4` | `v4.18.3` | `services/auth/go.mod` | Auth 当前使用。 |
| `github.com/jackc/pgx/v5` | `v5.7.6` | `services/file/go.mod`、`services/knowledge/go.mod`、`services/qa/go.mod`、`services/document/go.mod`、`services/ai-gateway/go.mod` | PostgreSQL client 目标基线；File、Knowledge、QA、Document、AI Gateway 当前使用，新增服务必须使用。 |
| `sqlc` generated packages | `v1.29.0`、`v1.31.1` | Generated headers under `services/*/internal/repository/sqlc/*.go` | Knowledge/QA 当前由 `sqlc v1.29.0` 生成；Auth/Document 当前由 `sqlc v1.31.1` 生成。变更某服务 SQL 后，按该服务 README 或 issue 要求使用 pinned 版本重新生成。 |
| `github.com/pressly/goose/v3` | `v3.27.1` | 技术选型基线 | 迁移工具版本固定；可用 CLI 或库方式接入。 |
| PostgreSQL | `16-alpine` | `services/qa/docker-compose.yml`、`services/qa/docker-compose.db.yml`、`services/document/docker-compose.yml` | 本地开发数据库。 |
| Redis | `7-alpine` | `services/qa/docker-compose.yml` | 本地队列、缓存、短期协调依赖。 |
| Qdrant | 待固定 | 尚无 Compose/runtime adapter | Knowledge 需要时补版本和运行配置。 |
| MinIO server | 待固定 | 尚无 Compose/部署版本锁定 | File MinIO adapter 已落地；补本地或部署依赖时固定版本。 |
| MinIO client (`mc`) | 待固定 | 尚无 Compose/部署版本锁定 | 本地 bucket 初始化方案待补。 |
| QA service image | 本地构建 | `services/qa/docker-compose.yml` | QA 本地 Compose 串联 auth/gateway/QA 数据库。 |
| Document service image | 本地构建 | `services/document/docker-compose.yml` | Document 本地 Compose 串联 PostgreSQL、migration 和服务。 |

## API 与契约版本

服务级机器可读契约在 `docs/services/<service>/api/` 下按调用面拆分：
`public.openapi.yaml` 只描述经 Gateway 暴露的 `/api/v1/**` 子契约，
`internal.openapi.yaml` 只描述服务间 `/internal/v1/**` 和健康检查契约。历史
`openapi.yaml` 文件按服务后续文档整理任务逐步迁移；新建服务或新增调用面应先按
public/internal 命名落位。

| 契约 | OpenAPI 版本 | API 文档版本 | 说明 |
| --- | --- | --- | --- |
| Gateway public API | `3.0.3` | `0.1.0` | 前端公开契约权威来源。 |
| Auth service API | `3.0.3` | `0.1.0` | 服务级身份与会话契约。 |
| AI Gateway internal API | `3.0.3` | `0.1.0` | 服务间模型配置和 OpenAI-compatible 调用契约。 |
| Parser public API | `3.0.3` | `0.1.0` | Parser 无 Gateway 公开 API；以空 `paths` 明确声明。 |
| Parser internal API | `3.0.3` | `0.1.0` | 服务间文档解析运行时契约，只供 Knowledge ingestion 等后端服务调用。 |
| QA service API | `3.0.3` | `0.1.0` | QA Agent Host 设计契约。 |
| Document service API | `3.0.3` | `0.1.0` | 报告生成设计契约。 |
| Knowledge service internal API | `3.0.3` | `0.1.0` | 服务内 OpenAPI 只覆盖已实现的基础知识库和文档上传/详情能力；更多公开能力以 gateway OpenAPI 为准。 |
| Knowledge public API draft | `3.0.3` | `0.1.0` | Knowledge 公开资源设计草案；稳定公开入口仍以 gateway OpenAPI 为准。 |
| File service API | `3.0.3` | `0.2.0` | File 服务是后端内部基础文件能力，不直接作为前端公开 API。 |

## 服务级偏离

| 服务 | 偏离项 | 原因 |
| --- | --- | --- |
| `knowledge` | 无。 | Knowledge 现在与仓库 Go 1.25 baseline 一致；仍沿用标准库 `net/http` / `http.ServeMux` 路由形态。 |

## 三选一决策记录

| 领域 | 备选 1 | 备选 2 | 备选 3 | 当前决定 | 版本状态 |
| --- | --- | --- | --- | --- | --- |
| 数据库访问 | `pgx` + 手写 SQL | `pgx` + `sqlc` | GORM/ent ORM | `pgx` + `sqlc` | `pgx/v5@v5.7.6` 已固定为目标基线；Knowledge/QA 使用 `sqlc v1.29.0`，Auth/Document 使用 `sqlc v1.31.1`，全仓 sqlc CLI 版本仍需后续统一 |
| 数据库迁移 | `goose` | `golang-migrate` | Atlas | `goose` | `goose@v3.27.1` 已固定 |
| 日志 | `slog` | `zap` | `zerolog` | `slog` | Go `1.25` 标准库 |
| HTTP 路由 | 标准库 `ServeMux` | `chi` | `gin` | 标准库 `ServeMux` | Go `1.25` 标准库 |
| 配置 | 手写 `os.Getenv` | `envconfig` | `viper` | `envconfig` 风格结构化加载 | 依赖待固定；允许先手写等价实现 |
| 队列 | Redis Streams 手写 | `asynq` | PostgreSQL queue | `asynq` | `asynq v0.26.0` 已固定 |
| 前端 API client | 手写 fetch 类型 | `openapi-typescript` + wrapper | Orval | `openapi-typescript` + wrapper | `openapi-typescript@7.13.0` 已固定；wrapper 已有 |
| 认证 token | Opaque token | JWT access + refresh | HttpOnly cookie session | Opaque Bearer token | 协议契约 |
| DOCX 生成 | Go DOCX 库 | Pandoc/LibreOffice | 独立模板服务 | Document worker + Pandoc/LibreOffice 类工具链 | 待固定 |

## 后端落地约定

### PostgreSQL、sqlc 和 pgx

- 每个需要 PostgreSQL 的服务在服务目录维护 `sqlc.yaml`。
- SQL 查询文件放在服务本地目录，例如：

```text
services/<service>/
  internal/repository/queries/
  internal/repository/sqlc/
  migrations/
  sqlc.yaml
```

- `sqlc` 生成代码只能被服务本地 repository 适配层使用，不直接泄露到 HTTP handler。
- 事务由 service/use-case 层发起；repository 接收 `pgx.Tx` 或抽象后的 querier。
- 查询必须显式列名，不使用 `SELECT *`。
- 用户输入只能通过参数绑定传入 SQL。
- 当前仓库同时存在 `pgx/v4@v4.18.3` 和 `pgx/v5@v5.7.6`。Auth 仍使用 `pgx/v4`；Knowledge、QA、Document、AI Gateway 使用 `pgx/v5`。新增服务和迁移后的服务必须使用 `github.com/jackc/pgx/v5`，不得再引入第三种数据库访问版本。
- 当前已生成的 sqlc 包仍存在 `v1.29.0` 和 `v1.31.1` 两个版本；新增或重生成某服务查询包时，必须在对应服务 README 或 issue 中固定命令并同步本文。变更 Knowledge SQL 后按 `services/knowledge/README.md` 中的 pinned `go run` 命令重新生成。

### goose 迁移

- 迁移文件继续放在 `services/<service>/migrations/`。
- 文件名使用有序前缀，例如 `0001_create_users.sql`。
- 首期允许 forward-only migration；如果写 down migration，必须能在本地和 CI 验证。
- CI 对有 SQL migration 的已落地 Go 服务执行迁移 apply 校验。
- `goose` 固定使用 `github.com/pressly/goose/v3@v3.27.1`；服务可按需要使用 CLI 或库方式接入，但 CI 和 README 必须引用同一版本。

### Redis 和 asynq

- Redis 队列统一使用 `asynq`。
- 任务类型命名使用 `<service>:<resource>:<action>`，例如 `knowledge:document:ingest`。
- 任务 payload 必须是 JSON，并包含可追踪字段：

```json
{
  "requestId": "req_123",
  "jobId": "job_123",
  "userId": "usr_123"
}
```

- 业务状态、任务最终状态、失败摘要和重试次数以 PostgreSQL 为权威；asynq 只负责排队、调度和执行。
- handler 不直接执行长任务，只创建业务 job 记录并投递 asynq task。
- 当前 Redis 本地版本为 `redis:7-alpine`；Knowledge 和 Document 已固定 `asynq v0.26.0`，并通过 asynq 依赖 `go-redis/v9 v9.14.1`。Gateway 直接使用 `go-redis/v9@v9.21.0`；后续应单独统一 Redis client 版本策略。

### 日志、指标和追踪

- 后端服务默认初始化 `slog.NewJSONHandler(os.Stdout, ...)`。
- 日志字段至少包含 `service`、`request_id`、`operation`、`status`；有用户上下文时可包含 `user_id`。
- 不记录密码、token、API key、数据库连接串、MinIO secret、prompt 全文、文档全文、object key 或 provider 原始响应体。
- 指标第一阶段采用 Prometheus 风格 endpoint；指标 label 不得包含用户输入正文、prompt、token、object key 或 API key 指纹。
- Prometheus client 和 OpenTelemetry SDK 版本尚未固定；接入时必须补充版本和采样、导出策略。

### Qdrant、MinIO 和对象边界

- Qdrant adapter 尚未落地；落地时优先使用服务内手写 HTTP client，不默认引入官方 client。
- Qdrant 只保存向量和最小 payload；展示正文、权限判断和状态判断必须回 PostgreSQL hydrate。
- File service 是 MinIO 对象存储边界；业务服务不得直接暴露 bucket、object key、内部 URL、access key 或 presigned URL。
- MinIO adapter 已在 File Service 落地，Go SDK 固定为 `github.com/minio/minio-go/v7@v7.2.1`；后续补本地 Compose 或生产部署时必须固定 MinIO server/client 镜像版本，并同步本文。

## 前端落地约定

- OpenAPI 类型生成统一使用 `openapi-typescript@7.13.0`；版本已写入 `apps/web/package.json` 和 `bun.lock`。
- 生成目录为 `apps/web/src/api/generated/`，生成文件不得手工修改。
- `apps/web/src/api/client.ts` 只负责 transport：base URL、认证头、request id、JSON/form/SSE 处理、envelope 和错误归一化。
- 前端不得继续依赖旧 `{ code, message, data }` envelope；gateway 项目自有 JSON 接口使用 `{ data, requestId }` 成功响应和 `{ error }` 错误响应。
- SSE 通过 `fetch` + stream reader 处理，必须支持 `AbortController` 取消。
- 当前 UI 生成配置来自 `components.json`：`base-nova`、Tailwind `neutral` base color、CSS variables、Lucide icons、`@` 指向 `apps/web/src`。
- 当前前端质量命令为 `bun run --cwd apps/web check` 和 `bun run --cwd apps/web build`。

## 安全落地约定

- `Authorization: Bearer <accessToken>` 中的 access token 是 opaque token。
- Auth 服务保存 token hash，不保存明文 access token。
- Gateway Redis 会话缓存 key 使用 token hash，不使用原始 token。
- 密码哈希使用 `argon2id-v1`；固定参数为 `m=65536 KiB`、`t=3`、`p=2`、`salt=16 bytes`、`key=32 bytes`，编码为 PHC string。
- AI Gateway provider API key 不进入日志、响应、指标 label 或前端缓存。
- AI Gateway provider API key 生产环境优先保存 secret manager 引用；第一阶段如果使用数据库加密列，必须保存加密密文、加密密钥版本和脱敏状态，不能保存明文。

## CI 和部署落地约定

- 当前 GitHub Actions 已固定 `actions/github-script@v7`，用于 PR guard、commitlint 和 auto-label。
- 当前 runner 使用 `ubuntu-latest`，这是 GitHub 托管滚动版本；如需完全可复现 CI，后续应改为团队认可的固定 runner 镜像或自托管 runner。
- Frontend CI 后续应执行 `bun install --frozen-lockfile`、`bun run --cwd apps/web check`、`bun run --cwd apps/web build`。
- Go Service CI 按服务路径执行 `go test ./...` 和 `go build ./cmd/server`。
- Goose migration CI 对有 SQL migration 的服务执行 `goose@v3.27.1` apply 校验。
- Docker 构建和部署流水线应按服务路径拆分，避免无关变更触发全量检查。

## 后续需要同步的实现任务

- 为尚未完成数据库 runtime repository 的 Go 服务补充或迁移 `sqlc.yaml`、query 文件和 `pgx` repository。
- 为后续新增的数据库服务同步 `goose@v3.27.1` 迁移命令和 CI 校验。
- 为需要异步任务的服务接入 `asynq` client/worker；Knowledge 已固定首个 asynq/go-redis 版本，后续服务接入前应复核是否沿用该版本。
- 前端接入 `openapi-typescript`，生成 gateway 类型，并固定生成器版本。
- 前端测试接入 Vitest、React Testing Library 和 Playwright，并固定版本。
- 本地 Compose 和生产部署补齐 Qdrant、MinIO、MinIO mc 等依赖时，必须使用固定镜像 tag，不能以 `latest` 作为生产基线。
- 为 Prometheus metrics、OpenTelemetry tracing、DOCX 工具链和 MCP SDK/sidecar 固定版本。
