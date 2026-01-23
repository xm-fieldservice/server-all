from __future__ import annotations

"""最小化测试脚本：模拟三栏 Alt+Enter 笔记入库链路。

运行方式（在 ai-factory 根目录下）：

    python test_entries_ingest_altenter.py

要求：
- 当前 Python 环境能够 `import ai_factory`；
- AI 工厂侧已正确配置数据库连接（AI_PG_*）和必要的模型/向量依赖；

脚本会尝试调用 entries_ingest(raw_text="测试11111")，并打印结果或错误。
"""

from datetime import datetime

from ai_factory.integrations.entries_ingest import entries_ingest


def main() -> None:
    raw_text = "测试11111"
    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    payload = {
        "raw_text": raw_text,
        "note_datetime": timestamp,
        # 与三栏约定保持一致：project_code/user_id 可选
        "project_code": None,
        "user_id": None,
        "extra_context": {
            "source": "altenter_test_script",
        },
    }

    print("[test] calling entries_ingest with payload:")
    print({k: v for k, v in payload.items() if k != "raw_text"})
    print("[test] raw_text:", raw_text)

    try:
        result = entries_ingest(payload)
    except Exception as exc:  # noqa: BLE001
        print("[test] entries_ingest FAILED:", repr(exc))
        raise

    print("[test] entries_ingest RESULT:")
    print(result)

    entries = (result or {}).get("entries") or []
    if not entries:
        print("[test] WARNING: result.entries is empty")
        return

    first = entries[0]
    entry_id = first.get("entry_id")
    title = first.get("title")
    print("[test] first entry_id =", entry_id)
    print("[test] first title    =", title)


if __name__ == "__main__":
    main()
