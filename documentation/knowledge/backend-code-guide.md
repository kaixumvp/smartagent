# Knowledge Hub — 后端代码导读

> 本文档面向"能读懂源码"的开发者，逐层拆解 `application/knowledge/backend/` 的
> 结构与实现。配套文档见 [`version-roadmap.md`](./version-roadmap.md)（版本规划）与
> [`enterprise-knowledge-hub-architecture-version-plan.md`](./enterprise-knowledge-hub-architecture-version-plan.md)（总体架构）。
> 版本线见仓库根 [`VERSIONS.md`](../../VERSIONS.md)。

---

## 1. 一句话架构

> **上传文件 → 解析成 Markdown → 切成 Chunk → 向量化 → 入库（Postgres 存元数据 + 向量库存向量）
> → 检索时混合召回（向量 + BM25）→ 重排 → 拼上下文。**

代码采用 **端口与适配器（Ports & Adapters）** 思想：核心逻辑只依赖 **Protocol（接口）**，
具体实现（内存索引 / Qdrant、本地目录 / MinIO、hash 向量 / HTTP 向量）都是可插拔的适配器，
由 `build_xxx()` 工厂函数按配置切换。

---

## 2. 目录结构

```
backend/
├── app/
│   ├── main.py          # FastAPI 入口：组装组件、启动后台 worker
│   ├── config.py        # 全部配置项（pydantic-settings）
│   ├── database.py      # SQLAlchemy engine / Session / Base
│   ├── models.py        # 5 张 ORM 表
│   ├── schemas.py       # Pydantic 请求/响应模型
│   ├── ids.py           # 主键生成 new_id + 时间 utcnow
│   ├── textutil.py      # 纯函数工具：分词 / 归一化 / hash 向量
│   ├── storage.py       # 对象存储：本地目录 / MinIO
│   ├── parse.py         # 文件解析：PDF/Word/Excel/PPT/图片/OCR
│   ├── chunking.py      # Markdown 按标题切块
│   ├── embedding.py     # 向量化：hash / HTTP
│   ├── index.py         # 向量索引：内存 / Qdrant + 元数据过滤
│   ├── retrieval.py     # 检索编排：分析→召回→融合→重排→上下文
│   ├── ingest.py        # 作业状态机：入队 + 处理
│   ├── deps.py          # FastAPI 依赖注入 + 内部密钥校验
│   └── routers/         # HTTP 路由
│       ├── bases.py     #   知识库 / 文件夹 CRUD
│       ├── documents.py #   文档上传/下载/删除/重建
│       ├── search.py    #   检索（公开 + 内部）
│       └── jobs.py      #   作业查询 / 手动跑一轮
├── tests/               # 33 个单测（零外部依赖）
├── pyproject.toml / Dockerfile / .env.example
```

依赖方向（自上而下，禁止反向 import）：

```text
routers → deps → (ingest / retrieval / parse / chunking / embedding / index / storage)
              → models / config / ids / textutil
```

路由层只做 HTTP 语义，业务编排在 `ingest` 与 `retrieval`，基础设施在底层。

---

## 3. 逐层详解

### 3.1 配置层 `config.py`

所有开关集中在 `Settings`（pydantic-settings），从环境变量 / `.env` 读取。
**默认值即"零依赖可跑"**，生产用环境变量切换。

| 配置 | 默认 | 含义 |
|---|---|---|
| `database_url` | `sqlite:///./data/knowledge.db` | 本地 SQLite；生产换 Postgres |
| `object_store_type` | `local` | 本地目录；`s3` 换 MinIO |
| `qdrant_url` | `""`（空） | 空 → 内存索引；填了接 Qdrant |
| `embedder` | `hash` | 无依赖伪向量；`http` 接真实模型 |
| `ocr_backend` | `none` | `tesseract` 启用 OCR |
| `reranker_backend` | `lexical` | 无依赖词法重排；`http` 接 cross-encoder |
| `worker_enabled` | `true` | 后台作业线程开关 |

**设计意图**：`hash` 向量 + 内存索引 + 本地目录 + SQLite 意味着**不配任何外部服务也能跑通全链路**——
为了可测试、可 Demo。生产时用环境变量切成真实组件。

### 3.2 基础工具 `ids.py` / `textutil.py`

- **`ids.py`**
  - `new_id("doc")` → `"doc_{32 位 hex}"`。主键在**应用层生成**（非数据库自增），
    同一套 ID 约定跨 SQLite/Postgres 复用，也便于分布式。
  - `utcnow()` → 带时区的 UTC 时间。

- **`textutil.py`**：四个纯函数，是系统最小的"原子能力"。
  - `tokenize(text)`：正则切词（`[A-Za-z0-9_]+|[一-鿿]`），英文单词/数字按词、中文按单字。
  - `l2_normalize(vec)`：L2 归一化（使余弦相似度 = 点积）。
  - `hashed_embedding(text, dim)`：**伪向量**——把每个 token 哈希到 `[0, dim)` 的桶 +1 再归一化。
    非真语义，但保证"相似文本 → 相似向量"，用于跑通链路与单测。
  - `term_overlap(q, text)`：查询词命中比例，供重排使用。

### 3.3 数据模型 `models.py` — 5 张表

领域层级为 **KB → Folder → Document → Chunk**，外加作业表：

```text
KnowledgeBase (kb) 1─┬─n Folder
                     └─n Document 1─n Chunk
                                     ProcessingJob (1 Document ↔ n Job)
```

| 表 | 关键字段 | 作用 |
|---|---|---|
| `knowledge_bases` | id, name, description | 知识库（资源容器） |
| `folders` | id, knowledge_base_id, parent_id | 树形文件夹（可选） |
| `documents` | id, kb_id, folder_id, filename, **status**, parser_name, ocr_used, **original_key / markdown_key** | 文档元数据 + 状态机 + 对象存储 key |
| `chunks` | id, document_id, kb_id, **text, heading_path, start_offset, end_offset** | 切好的块，带**出处**（偏移量） |
| `processing_jobs` | id, document_id, kind, **status**, error, started_at/finished_at | 异步解析作业 |

**两个关键设计**（对应 roadmap 的"所有知识可追溯"）：

1. **`status` 状态机**：`pending → processing → ready / failed`。上传即 `pending`，后台 worker 处理后 `ready`。
2. **对象存储分离**：文件字节不塞数据库，只存 key（`original_key` / `markdown_key`），
   实际内容放对象存储（本地目录或 MinIO）。

### 3.4 端口层（Protocol）—— 架构骨架

核心逻辑**不 import 具体实现，只依赖接口**。这些 Protocol 分布在各自文件里：

| 文件 | Protocol | 方法 |
|---|---|---|
| `storage.py` | `ObjectStore` | `put / get / delete` |
| `parse.py` | `OcrEngine` | `transcribe` |
| `embedding.py` | `Embedder` | `embed(texts) -> vectors` |
| `index.py` | `VectorIndex` | `upsert / delete_document / search` |
| `retrieval.py` | `Reranker` | `rerank(...)` |

每个 Protocol 至少两个实现（适配器），由 `build_xxx()` 按配置选择。
**加真实向量库 / 真实 embedding，只需新增一个类 + 一行工厂判断，不动核心逻辑。**

### 3.5 解析 `parse.py` + 切分 `chunking.py`

**`parse.py`** 把任意格式文件 → Markdown 字符串：

- `sniff_kind(filename, content_type)`：按后缀 + MIME 判型（md/pdf/docx/xlsx/pptx/image/binary）。
- 每种类型一个函数：`_pdf_text`（pypdf）、`_docx_text`（python-docx）、`_xlsx_text`（openpyxl）、`_pptx_text`（python-pptx）。
- **OCR 兜底**：PDF 抽出文本过少（`len(tokenize(text)) < 12`，即扫描件）或图片类型时，调 `ocr.transcribe` 走 tesseract。
- 统一产出 `ParseResult(markdown, parser_name, ocr_used)`。

**`chunking.py`** 把 Markdown → 若干 `ChunkDraft`：

- `HEADING_RE` 匹配 `#~######` 标题。
- 按标题分节，维护"标题栈"算 `heading_path`（如 `第一章 / 1.2 背景`）。
- 每节用 `_split_long` 按 `max_chars=800`、`overlap=120` 切长块，并**记录 `start_offset / end_offset`**——
  这就是"可追溯出处"的来源。

### 3.6 向量索引 `index.py`

- `InMemoryVectorIndex`：一个 dict，`search` = 过滤 + 归一化点积 + 排序，O(n) 但零依赖，够测试和小数据。
- `QdrantVectorIndex`：真向量库，`upsert` 写 point，`search` 用 `Filter` 做元数据过滤。
- **`SearchFilter`**（dataclass）：`kb_ids / folder_id / mime_types / created_after / created_before`。
  v0.2 的"元数据过滤"能力——**只按资源属性过滤，不按用户身份过滤**（权限放到 v0.7）。
- `_stable_uuid`：把字符串 chunk_id 稳定映射成 Qdrant 需要的 UUID。

### 3.7 检索编排 `retrieval.py` —— v0.2 核心

`RetrievalService.search()` 是入口，流程：

```text
1. analyze_query(query) → 判断意图
     ├─ 有引号 / 编号(如 XK-4021) → keyword
     ├─ 词数 ≤2                 → semantic
     └─ 否则                    → hybrid

2. 双路召回（可被 mode 裁剪）
     ├─ dense：embed(query) → 向量索引 search → top pool
     └─ sparse：BM25 对所有 chunk 打分 → top pool

3. rrf_fuse([dense_rank, sparse_rank]) → 倒数排名融合（RRF）

4. rerank（可选）→ 词法重排或 HTTP cross-encoder 精排

5. 取 top_k → 拼 evidence + build_context（去重截断拼引用块）
```

关键实现细节：

- **`mode`**（`hybrid / vector / keyword`）为 v0.2 验收设计——对比纯向量 vs 混合。
- **`pool = top_k * 4`**：先多召回候选再重排截断，避免"各自只给 top_k 融合后遗漏"。
- **四档得分全返回**：`dense_score / sparse_score / fused_score / rerank_score`，便于观察每一路效果。
- **`bm25_scores`** 是标准 BM25（含 IDF、长度归一化），**`rrf_fuse`** 是 RRF（`1/(k+rank)`），
  **`lexical_rerank`** 是词重叠加权 + 引号短语加成。

### 3.8 作业状态机 `ingest.py`

后台解析用**作业队列**模式，而非同步阻塞：

- `enqueue_ingest(db, doc_id)`：上传时只插一条 `status=queued` 的 `ProcessingJob`，立刻返回（上传不阻塞）。
- `process_next_job(...)`：取最早的 `queued` → 置 `running` → 调 `ingest_document` →
  成功置 `succeeded`，失败置 `failed` 并回写文档状态。
- `ingest_document(...)`：**完整解析流水线**——取原文 → parse → 存 Markdown → 删旧 chunk →
  重新切块 → 向量化 → 写 chunk + 索引 → 置 `ready`。

`process_next_job` 一次只处理一个作业。`main.py` 的 `_worker_loop` 后台循环反复调它（间隔 0.5s）；
`routers/jobs.py` 也暴露手动 `/jobs/process` 跑一轮（测试/Demo 用）。

### 3.9 存储 `storage.py`

- `LocalObjectStore`：根目录 + key 拼路径，`put/get/delete` 读写本地文件。
- `S3ObjectStore`：用 `minio` SDK（**懒加载** import，避免不装 minio 时强依赖），自动建 bucket。
- key 约定：`originals/{kb_id}/{doc_id}/{filename}` 与 `parsed/{kb_id}/{doc_id}.md`。

### 3.10 API 层 `schemas.py` + `routers/` + `deps.py` + `main.py`

- **`schemas.py`**：Pydantic 模型，`Out` 类带 `from_attributes=True`（ORM 直接序列化）。
  `SearchRequest` 的 `mode / rerank / kb_ids / mime_types` 对应检索参数。
- **`routers/`**：薄 HTTP 语义层，**不做业务逻辑**，只取参数 → 调 service/ingest → 返回。
  - `bases.py`：`/v1/knowledge-bases` 与 `/folders`。
  - `documents.py`：上传（`def` 同步函数 + `file.file.read()`，让 FastAPI 用线程池处理阻塞 I/O）、
    下载原文/Markdown、重建索引、删除。
  - `search.py`：公开 `/v1/search` + 内部 `/internal/search`（带共享密钥，供平台 adapter 用）。
  - `jobs.py`：作业查询 + 手动 `/jobs/process`。
- **`deps.py`**：把 `app.state` 里组装的组件（store/embedder/index/ocr/retrieval）用 `Depends` 注入路由。
  `require_integration_key` 校验 `X-Integration-Key` 头（未配密钥时放行）。
- **`main.py`**：`build_components()` 组装组件放 `app.state`；`lifespan` 里 `create_all` 建表 + 启动后台 worker；
  CORS `*`；挂载全部路由。

---

## 4. 两条核心数据流

### 4.1 写入流：上传 → 可检索

```text
POST /v1/knowledge-bases/{kb}/documents  (documents.py: upload_document)
  │  1. 存原文件到对象存储 → original_key
  │  2. 建 Document(status=pending)
  │  3. enqueue_ingest → ProcessingJob(queued)
  ▼
后台 worker (main.py: _worker_loop)
  ▼
ingest.process_next_job → ingest_document
  │  1. store.get(original_key) 取原文
  │  2. parse_bytes → Markdown → 存 parsed/{doc}.md
  │  3. 删旧 Chunk + 旧向量
  │  4. chunk_markdown → 若干 ChunkDraft
  │  5. embedder.embed → 向量
  │  6. 写 Chunk(带 start/end_offset) + index.upsert
  └  7. Document.status = ready
```

### 4.2 读取流：query → 结果

```text
POST /v1/search (search.py) → RetrievalService.search
  │  1. analyze_query 判意图
  │  2. 向量召回 (index.search) + BM25 (bm25_scores)
  │  3. rrf_fuse 融合
  │  4. rerank 重排
  │  5. 取 top_k → 拼 evidence + context
  ▼
SearchResponse { chunks[], analysis, mode, rerank_applied, context }
```

---

## 5. 关键设计决策

| 决策 | 原因 |
|---|---|
| **默认全"假"组件**（hash 向量/内存索引/本地目录/SQLite） | 零依赖可跑、可单测、可 Demo；生产换真组件 |
| **端口与适配器** | 换 Qdrant/MinIO/真实 embedding 只加适配器，不动核心逻辑 |
| **ID 应用层生成** | 跨库一致、便于分布式、可追溯 |
| **对象存储分离** | 大文件不进数据库，只存 key |
| **作业状态机 + 后台 worker** | 上传不阻塞；解析失败可重试、可追溯 |
| **Chunk 带偏移量** | 每条命中能点回原文，这是知识库"可信"的根基 |
| **四档得分全返回** | 便于观察召回/融合/重排每路效果（v0.2 验收要对比） |
| **管理 API 无鉴权、内部 API 共享密钥** | 对齐 Capability Registry 的 MVP 约定；权限最后设计（v0.7） |
| **测试零外部依赖** | conftest 用 SQLite 临时文件 + 内存索引 + hash 向量，33 个单测无需 PG/MinIO/Qdrant/LLM |

---

## 6. 从代码导航

- 想理解"一个请求怎么进来"：`main.py` → `routers/*.py` → `deps.py`。
- 想理解"解析流水线"：`ingest.py` → `parse.py` → `chunking.py` → `embedding.py` → `index.py`。
- 想理解"检索算法"：`retrieval.py`（`analyze_query` / `bm25_scores` / `rrf_fuse` / `lexical_rerank` / `build_context`）。
- 想理解"怎么换真实组件"：各 `build_xxx()` 工厂函数 + `config.py` 的环境变量。
