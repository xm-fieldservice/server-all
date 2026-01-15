from __future__ import annotations

"""针对短文本 NOTE 的入库链路行为做回归测试的脚本。

用途：
- 构造多种极短 / 较短的笔记原文，调用 entries_ingest；
- 仅在控制台打印生成的 title 和 summary，不写入数据库；
- 帮助观察短文本场景下是否仍然存在过度脑补问题。

使用方法（在 ai-factory 根目录，已激活 .venv）：

    python debug_entries_ingest_note_short_inputs.py

"""

from typing import Any, Dict, List

from ai_factory.integrations.entries_ingest import entries_ingest


TEST_CASES: List[str] = [
    "测试笔记一",
    "测试笔记一\n标签: 治疗+方案",
    "TODO: 明天补写 RAG 架构讨论纪要",
    "仅供测试的极短记录",
]


def main() -> None:
    for idx, text in enumerate(TEST_CASES, start=1):
        print("\n=== CASE", idx, "===")
        print("raw_text =", repr(text))

        payload: Dict[str, Any] = {"raw_text": text}

        try:
            result = entries_ingest(payload)
        except Exception as exc:  # noqa: BLE001
            print("entries_ingest FAILED:", repr(exc))
            continue

        print("entries_ingest SUCCEEDED")
        print("result =", result)


if __name__ == "__main__":
    main()
