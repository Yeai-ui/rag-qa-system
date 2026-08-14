# 端到端冒烟测试脚本（离线模式：hash embedding + echo LLM）
# 用法：.venv/Scripts/python.exe tests/smoke_test.py
# 覆盖：健康检查 → 注册 → 建库 → 上传文档 → 解析 → 非流式问答 → 会话历史 → 统计
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
TOKEN = ""


def req(method, path, body=None, token=None, raw=False):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            text = resp.read().decode()
            return resp.status, (text if raw else json.loads(text))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]


def check(name, cond, extra=""):
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name} {extra}")
    return cond


def main():
    code, health = req("GET", "/api/health")
    ok1 = check("健康检查", code == 200 and health.get("status") == "ok", str(health))

    code, reg = req("POST", "/api/auth/register", {"username": "tester", "password": "test123456"})
    if code == 200 and "access_token" in reg:
        ok2 = check("注册", True)
    else:
        # 用户已存在 -> 尝试登录（幂等）
        code, reg = req("POST", "/api/auth/login", {"username": "tester", "password": "test123456"})
        ok2 = check("注册(已存在,改用登录)", code == 200 and "access_token" in reg)
    global TOKEN
    TOKEN = reg.get("access_token", "")

    code, kbs = req("GET", "/api/kb", token=TOKEN)
    ok3 = check("知识库列表", code == 200 and isinstance(kbs, list))

    code, kb = req("POST", "/api/kb", {"name": "测试知识库", "description": "冒烟测试"}, token=TOKEN)
    ok4 = check("新建知识库", code == 200 and kb.get("id"), str(kb))
    kb_id = kb.get("id")

    # 构造一个临时文本文档（含可检索内容）
    doc_path = "data/uploads/smoke_doc.txt"
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write("《系统使用说明》\n\n")
        f.write("本系统的请假流程如下：员工需提前一天在系统中提交请假申请，"
                "注明请假类型、起止日期与事由，经直属主管审批后生效。\n\n")
        f.write("系统支持上传 PDF、DOCX、Markdown 与 TXT 格式文档，"
                "上传后自动完成解析、切分与向量化入库。\n\n")
        f.write("系统基于检索增强生成技术，回答问题时先检索知识库中的相关文本，"
                "再交由大语言模型组织答案，并在回答中标注引用来源。\n")

    # 上传（multipart）
    boundary = "----smoketest"
    with open(doc_path, "rb") as f:
        content = f.read()
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="smoke_doc.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    import urllib.request as u

    url = BASE + f"/api/kb/{kb_id}/docs"
    req2 = u.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Authorization": f"Bearer {TOKEN}"},
        method="POST",
    )
    with u.urlopen(req2, timeout=180) as resp:
        doc = json.loads(resp.read().decode())
    ok5 = check("上传并解析文档", doc.get("status") == "ready" and doc.get("chunk_count", 0) > 0,
                f"chunks={doc.get('chunk_count')}")

    code, ask = req("POST", "/api/chat/ask", {"query": "请假流程是什么？", "kb_id": kb_id}, token=TOKEN)
    ok6 = check("非流式问答", code == 200 and bool(ask.get("answer")), f"sources={len(ask.get('sources', []))}")

    code, convs = req("GET", "/api/chat/conversations", token=TOKEN)
    ok7 = check("会话列表", code == 200 and len(convs) >= 1)

    conv_id = convs[0]["id"]
    code, msgs = req("GET", f"/api/chat/conversations/{conv_id}/messages", token=TOKEN)
    ok8 = check("消息历史", code == 200 and len(msgs) >= 2, f"msgs={len(msgs)}")

    code, stats = req("GET", "/api/stats", token=TOKEN)
    ok9 = check("统计接口", code == 200 and stats.get("doc_count") >= 1, str(stats.get("kb_stats")))

    results = [ok1, ok2, ok3, ok4, ok5, ok6, ok7, ok8, ok9]
    print("\n===== 结果: %d/%d 通过 =====" % (sum(results), len(results)))
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
