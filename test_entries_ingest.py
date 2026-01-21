"""本地调试脚本：在内存中模拟规整 Agent 对“单条工作记录”的处理，不写入数据库。

用法：在 ai-factory 根目录下运行：

    python test_entries_ingest.py

脚本会读取 `工作记录测试样例.md` 全文作为 raw_text，
将“整条工作记录”视为一个自然条目，并生成四个字段：
- id: 占位ID；
- title: 由 Agent 根据原文生成的标题（此处为占位实现）；
- summary: 由 Agent 根据原文生成的内容概述（此处为占位实现，约200~300字以内）；
- content: 原文全文。
在终端打印这四个字段，便于检查形状是否合规。
"""

from __future__ import annotations

from pathlib import Path
from textwrap import shorten
from typing import Any, Dict, List

import uuid


def simulate_ingest_single_record(raw_text: str, base_meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """模拟“单条工作记录”的规整结果（不写库），严格输出四个字段：

    - id: 占位ID；
    - title: 标题（此处占位实现，用首行近似模拟，将来由 LLM 生成）；
    - summary: 内容概述（此处占位实现，截断到约200~300字，将来由 LLM 生成）；
    - content: 原文全文。
    """

    base_meta = base_meta or {}

    entry_id = base_meta.get("entry_id_prefix", "ent_") + str(uuid.uuid4())

    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    title = lines[0][:80] if lines else "工作记录"

    # 简单 summary：截取一定长度（约200~300字），后续由 LLM 替换
    plain = " ".join(lines)
    max_len = 260
    summary = plain[:max_len] + ("..." if len(plain) > max_len else "")

    record: Dict[str, Any] = {
        "id": entry_id,
        "title": title,
        "summary": summary,
        "content": raw_text,
    }
    # 透传基础元数据
    record.update({k: v for k, v in base_meta.items() if k not in record})

    return record


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    sample_path = repo_root / "工作记录测试样例.md"

    if not sample_path.exists():
        raise FileNotFoundError(f"找不到样例文件: {sample_path}")

    raw_text = sample_path.read_text(encoding="utf-8")

    print("=== 本地模拟规整 Agent（单条工作记录，不写数据库） 开始 ===")

    record = simulate_ingest_single_record(raw_text, base_meta={
        "project_code": "proj-ai-factory",
        "user_id": "u_local",
        "source": "local_debug_script",
    })

    snippet = shorten(str(record["content"]).replace("\n", " "), width=80, placeholder="...")

    print("id      :", record["id"])
    print("title   :", record["title"])
    print("summary :", record["summary"])
    print("content :", snippet)

    print("=== 本地模拟规整 Agent 结束 ===")


if __name__ == "__main__":
    main()
