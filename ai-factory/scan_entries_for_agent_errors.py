from __future__ import annotations

"""扫描 entries 表中可能存在入库 Agent 异常的记录。

规则（v0）：
- title 为空或全是空白；
- 或 summary_ai 为空；
- 或 summary_ai 中包含以下任一关键字：
  - "调用 Ollama 失败"
  - "LLM 输出无法解析为 JSON"
  - "解析 Ollama 返回 JSON 失败"

脚本只读数据库，不做任何修改，按时间倒序检查最近 N 条记录（默认 500 条）。
"""

from typing import Any, Dict, List

from ai_factory.db.pgvector_client import connection_scope


def fetch_recent_entries(limit: int = 500) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM entries ORDER BY created_at DESC LIMIT %s"
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]
    return [dict(zip(colnames, row)) for row in rows]


ERROR_KEYWORDS = [
    "调用 Ollama 失败",
    "LLM 输出无法解析为 JSON",
    "解析 Ollama 返回 JSON 失败",
]


def is_suspicious(entry: Dict[str, Any]) -> bool:
    title = str(entry.get("title") or "").strip()
    summary = str(entry.get("summary_ai") or "").strip()

    if not title:
        return True
    if not summary:
        return True

    for kw in ERROR_KEYWORDS:
        if kw in summary:
            return True
    return False


def main() -> None:
    entries = fetch_recent_entries(500)
    suspicious = [e for e in entries if is_suspicious(e)]

    print(f"最近检查 entries 数量: {len(entries)}")
    print(f"疑似 Agent 异常记录数量: {len(suspicious)}")

    for idx, e in enumerate(suspicious, start=1):
        print("\n--- 可疑记录 #", idx, "---")
        print("entry_id   :", e.get("entry_id"))
        print("created_at :", e.get("created_at"))
        print("title      :", repr((e.get("title") or "").strip())[:200])
        print("summary_ai :", repr((e.get("summary_ai") or "").strip())[:400])


if __name__ == "__main__":
    main()
