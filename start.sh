#!/usr/bin/env bash
# 智能知识问答系统 - 一键启动 (Linux/macOS)
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[1/4] 创建虚拟环境..."
  python3 -m venv .venv
fi

if [ ! -f ".venv/bin/fastapi" ] && [ ! -d ".venv/lib/python*/site-packages/fastapi" ]; then
  echo "[2/4] 安装依赖..."
  .venv/bin/pip install -r requirements.txt
fi

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "[3/4] 已生成 .env，请编辑其中的 LLM_API_KEY"
fi

echo "[4/4] 启动服务: http://127.0.0.1:8000"
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
