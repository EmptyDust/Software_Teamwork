# Parser Runtime Service

Parser 是内部文档解析运行时服务，由 Knowledge ingestion 和 QA 会话附件解析调用，不通过
public gateway API 暴露给前端。

## 职责边界

Parser 只负责把原始文档 bytes 转成规范化解析结果。默认目标后端是
Python + PaddleOCR PP-StructureV3，用于扫描 PDF、图片、表格、公式、图表、
印章和 OCR-heavy 版式；旧的 PaddleOCR 行级 OCR 后端只作为兼容模式保留。

Knowledge 仍然负责：

- 知识库文档资源、processing job 和公开文档状态。
- 从 File Service 获取原始文件引用和做业务可见性校验。
- 切片、chunk 持久化、embedding 生成、Qdrant 写入和检索 hydrate。
- 管理端 parser runtime configuration 的公开 gateway 契约。

QA 负责会话附件元数据、解析状态、临时 chunk、附件 owner 授权和 TTL 清理。Parser
不保存知识库、文档、QA 会话附件、chunk、embedding、Qdrant point、临时附件 chunk 或权限事实；也不得返回 object key、bucket、内部 URL、签名 URL、provider body、API key、prompt 或完整调试日志。

## 内部 API

Parser 的服务间契约是：

```text
POST /internal/v1/parsed-documents
```

机器可读契约分为两份：

- [`api/public.openapi.yaml`](api/public.openapi.yaml)：Parser 没有 Gateway 公开路径，前端、管理端和 MCP 调用方不得直连 Parser。
- [`api/internal.openapi.yaml`](api/internal.openapi.yaml)：Parser 服务间内部契约，当前供 Knowledge ingestion 和 QA 会话附件解析调用。
- [`docs/permission-matrix.md`](docs/permission-matrix.md)：Parser 内部服务认证、调用方白名单和 owner service 授权责任。
- [`docs/implementation.md`](docs/implementation.md)：当前实现状态、缺口、测试和最近检查记录。

Knowledge 调用 Parser 时必须传递 `X-Request-Id`、`X-Caller-Service: knowledge` 和必要的内部 service token。QA 会话附件解析调用必须传递 `X-Caller-Service: qa`。`X-User-Id` 只作为审计上下文，不作为 Parser 里的授权事实。

## 运行时方向

Parser 是使用 `uv` 管理的 Python 服务。它用 FastAPI 提供内部 HTTP API，直接解析
TXT/Markdown 和 Office OpenXML 格式，并把 PDF/image 路径默认路由到 PaddleOCR
PP-StructureV3，以 Markdown 作为结构化文本的主输出。
Go 服务只通过 HTTP 调用 Parser，不应在 Knowledge 进程中引入 PaddleOCR、
PaddlePaddle、OpenCV、CUDA 或模型加载依赖。
Docker 容器入口是 `parser-service`；宿主机直接开发时才使用 `uv run parser-service`。

## 实现状态

当前代码状态、测试入口、真实 PaddleOCR smoke、缺口和最近检查记录统一维护在 [`docs/implementation.md`](docs/implementation.md)。本文档只保留 Parser 的职责边界、服务间契约和稳定运行时方向；实现缺口不在 README 重复维护。
