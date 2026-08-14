# 基于大语言模型的智能领域知识问答系统（RAG）

一个**可用于毕业设计、软件著作权申请、简历项目**的完整 RAG（Retrieval-Augmented Generation，检索增强生成）应用：
上传领域文档（PDF / DOCX / MD / TXT）构建个人知识库，基于大模型进行**带引用来源**的智能问答。

## 功能特性

| 模块 | 说明 |
|------|------|
| 用户系统 | 注册 / 登录（JWT 鉴权） |
| 知识库管理 | 多知识库、文档上传、解析状态、删除/重试 |
| RAG 问答 | 向量语义检索 + BM25 关键词检索（RRF 融合），回答自动标注引用 [1][2] |
| 流式输出 | SSE 逐字输出，交互体验接近 ChatGPT |
| 会话管理 | 多会话、历史消息、自动标题 |
| 数据统计 | 知识库/文档/文本块/会话/消息仪表盘 |
| 文档解析 | PDF、DOCX（含标题识别）、Markdown、TXT（GBK 自动兼容） |

## 技术栈

- **后端**：Python / FastAPI / SQLAlchemy / SQLite
- **RAG 管线**：自研 Pipeline（解析 → 递归切分 → 向量化 → 混合检索 → Prompt 组装 → LLM 生成）
- **向量检索**：ChromaDB（持久化，无需单独部署）
- **混合检索**：向量相似度 + BM25（jieba 分词），RRF 算法融合
- **大模型**：OpenAI 兼容 API（OpenAI / DeepSeek / 智谱 / 通义 / 硅基流动 / Ollama 均可）
- **前端**：原生 HTML/CSS/JS（零依赖，离线可用）

## 目录结构

```
rag-qa-system/
├── app/
│   ├── main.py          # FastAPI 入口
│   ├── db.py            # SQLite 初始化
│   ├── models.py        # ORM 模型（用户/知识库/文档/文本块/会话/消息）
│   ├── schemas.py       # Pydantic 契约
│   ├── core/            # 配置(config) + 安全(security/JWT)
│   ├── api/             # 认证/知识库/对话/统计 路由
│   ├── rag/             # RAG 核心（loader/splitter/embedder/retriever/generator/prompts/pipeline）
│   └── web/             # 前端（index.html / style.css / app.js）
├── data/                # SQLite、上传文件、向量库（运行时生成）
├── docs/                # 设计方案 / 软著材料
├── .env.example         # 环境配置模板
├── requirements.txt
├── start.bat / start.sh # 一键启动
```

## 快速开始（3 分钟）

### 方式一：一键脚本

**Windows**：双击 `start.bat`（自动创建虚拟环境、安装依赖、生成 .env、启动服务）
**Linux/macOS**：`bash start.sh`

### 方式二：手动

```bash
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate         # Linux/macOS
pip install -r requirements.txt

# 2. 配置 .env
cp .env.example .env              # Windows: copy .env.example .env
# 编辑 .env：填入 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL

# 3. 启动
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

打开浏览器访问 **http://127.0.0.1:8000** 即可。

## 离线演示模式（无 API Key 也能跑通全流程）

`.env` 中默认已配置离线演示：

```ini
LLM_PROVIDER=echo        # 模型返回模拟回答，验证问答流程
EMBEDDING_PROVIDER=hash  # 使用确定性哈希向量，验证检索流程（语义效果有限）
```

演示模式下可以完整走通：**注册登录 → 新建知识库 → 上传文档 → 解析 → 检索 → 问答 → 引用展示**，适合开发调试与演示。

配置真实 API Key 后改为：

```ini
LLM_PROVIDER=api
LLM_API_KEY=sk-xxxxxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

EMBEDDING_PROVIDER=api
EMBEDDING_API_KEY=sk-xxxxxx
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
```

> 也可以使用 `EMBEDDING_PROVIDER=local` + `pip install sentence-transformers` 在本地 CPU 跑 `BAAI/bge-small-zh-v1.5`。

## API 一览（Swagger: http://127.0.0.1:8000/docs）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/register | 注册 |
| POST | /api/auth/login | 登录 |
| GET  | /api/kb | 知识库列表 |
| POST | /api/kb | 新建知识库 |
| DELETE | /api/kb/{id} | 删除知识库 |
| GET  | /api/kb/{id}/docs | 文档列表 |
| POST | /api/kb/{id}/docs | 上传文档（自动解析入库） |
| DELETE | /api/kb/{id}/docs/{did} | 删除文档 |
| GET  | /api/chat/conversations | 会话列表 |
| POST | /api/chat/conversations | 新建会话 |
| POST | /api/chat/ask | 非流式问答 |
| POST | /api/chat/ask-stream | 流式问答（SSE） |
| GET  | /api/stats | 统计信息 |

## 常见问题

- **端口被占用**：修改 `.env` 中 `PORT`，或启动时 `--port 8001`
- **PDF 扫描件无法解析**：pypdf 不支持扫描件 OCR，请使用文本型 PDF
- **回答质量不理想**：调大 `TOP_K`、减小 `CHUNK_SIZE`，或在知识库中补充更相关文档
- **Embedding 报错 401**：检查 `.env` 中 `EMBEDDING_API_KEY`（未单独设置时复用 `LLM_API_KEY`）

## 文档

- `docs/毕业设计-设计方案.md` — 完整设计方案（架构图/数据库/排期/答辩要点/实验方案）
- `docs/软著申请-技术文档模板.md` — 软件著作权申请材料模板

## 免责声明

本项目用于学习、毕业设计与演示用途。接入第三方大模型 API 产生的费用由使用者自行承担。
