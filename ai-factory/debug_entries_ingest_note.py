from __future__ import annotations

"""独立调试 NOTE 入库链路的脚本。

用途：
- 绕开三栏页面，直接在本地虚拟环境里调用 entries_ingest；
- 验证 DeepSeek NOTE Agent 是否还能正常工作（网络 / 配置 / 提示词问题）；
- 出错时打印尽可能多的上下文，便于排查。

使用方法（在 ai-factory 根目录，已激活 .venv）：

    python debug_entries_ingest_note.py

如需修改测试文本，可以直接编辑本文件中的 TEST_RAW_TEXT。
"""

import os
from typing import Any, Dict

from ai_factory.integrations.entries_ingest import entries_ingest


# 可以直接在这里换成你想测试的一段 NOTE 文本
TEST_RAW_TEXT = """昨天我们运行了一个DB标题和summary改造脚本，批量处理。我们今天要围绕昨天的这个行动做两件事：\n1. ...\n2. ..."""


def main() -> None:
    print("[debug_entries_ingest_note] START")

    print("INGEST_MODEL_NAME =", os.getenv("INGEST_MODEL_NAME"))
    print("INGEST_MODEL_BASE_URL =", os.getenv("INGEST_MODEL_BASE_URL"))
    print("DEEPSEEK_API_KEY set =", bool(os.getenv("DEEPSEEK_API_KEY")))

    payload: Dict[str, Any] = {
        "raw_text": TEST_RAW_TEXT,
        # 如有需要，可以在这里补充 project_code / user_id / note_datetime
        # "project_code": "beibei",
        # "user_id": "local-debug",
    }

    try:
        result = entries_ingest(payload)
    except Exception as exc:  # noqa: BLE001
        print("[debug_entries_ingest_note] entries_ingest FAILED:", repr(exc))
        return

    print("[debug_entries_ingest_note] entries_ingest SUCCEEDED")
    print("result =", result)


if __name__ == "__main__":
    main()
