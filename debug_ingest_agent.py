"""一体化调试脚本：调用规整 Agent 完成两步测试。

前提：
- 已在 D:\AI\desktop_app\config\ 下准备好规整 Agent 的配置 JSON，
  例如：D:\AI\desktop_app\config\agents\ingest_agent.json
- 该配置可被 config.run_agent.run_agent_once 正常加载，并连通 deepseek-14b 等模型。

本脚本执行两步：
1. 向规整 Agent 发送 "你是谁？"，检查自我介绍是否符合预期角色；
2. 读取 `工作记录测试样例.md`，让规整 Agent 按约定输出四个字段：
   - id: 占位ID；
   - title: 标题；
   - summary: 内容概述（约200~300字内）；
   - content: 原文全文。

用法（在 D:\AI\ai-factory 根目录下）：

    python debug_ingest_agent.py

如需修改 Agent 配置路径，可调整 CONFIG_PATH 常量。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# === 配置区：根据需要修改 ===
# 规整 Agent 的配置 JSON 路径（请按实际路径调整）
CONFIG_PATH = r"D:\AI\desktop_app\config\agents\ingest_agent.json"

# desktop_app 根目录，用于导入 config.run_agent
DESKTOP_APP_ROOT = Path(r"D:\AI\desktop_app")

# 工作记录样例文件
SAMPLE_RECORD_PATH = Path(__file__).resolve().parent / "工作记录测试样例.md"


def _ensure_import_run_agent():
    """将 desktop_app 加入 sys.path，导入 run_agent_once。"""

    config_dir = DESKTOP_APP_ROOT / "config"
    if str(config_dir) not in sys.path:
        sys.path.insert(0, str(config_dir))

    try:
        import run_agent  # type: ignore
    except Exception as e:  # pragma: no cover - 调试时显式报错
        raise ImportError(f"无法从 {config_dir} 导入 run_agent.run_agent_once: {e}")

    return run_agent.run_agent_once


def _step0_testpoint_echo(run_agent_once_func) -> None:
    """步骤0：测试点 T1：固定字符串回显。"""

    print("=== 步骤0：测试点 T1（固定字符串回显） ===")

    prompt = (
        "请你只回复下面这一行内容，不要多任何一个字、任何标点，也不要换行：\n"
        "TESTPOINT_T1_OK"
    )

    response = run_agent_once_func(
        config_path=CONFIG_PATH,
        user_input=prompt,
        memory_policy=None,
        verbose=True,
    )

    print("--- Agent 对 T1 的回答 ---")
    print(response)
    print("=== 步骤0结束 ===\n")


def _step1_self_introduction(run_agent_once_func) -> None:
    """步骤1：问 Agent “你是谁？”。"""

    print("=== 步骤1：自我介绍 - 你是谁？ ===")

    prompt = "你是谁？请用中文作自我介绍，不要回答‘我还没有学会回答这个问题’。"

    response = run_agent_once_func(
        config_path=CONFIG_PATH,
        user_input=prompt,
        memory_policy=None,
        verbose=True,
    )

    print("--- Agent 自我介绍 ---")
    print(response)
    print("=== 步骤1结束 ===\n")


def _step2_process_sample_record(run_agent_once_func) -> None:
    """步骤2：让 Agent 加工样例工作记录为四字段。"""

    print("=== 步骤2：加工工作记录样例（生成 id/title/summary/content） ===")

    if not SAMPLE_RECORD_PATH.exists():
        raise FileNotFoundError(f"找不到工作记录样例文件: {SAMPLE_RECORD_PATH}")

    raw_text = SAMPLE_RECORD_PATH.read_text(encoding="utf-8")

    prompt = f"""
下面是一条完整的工作记录，请你严格按下面要求输出一个 JSON 对象：

字段要求：
1. id: 任意字符串ID（可以使用占位符，例如 "ent_xxx"），只需在本次输出中唯一即可。
2. title: 根据工作记录内容生成的中文标题，简短但能概括主要内容。
3. summary: 用中文对工作记录做内容概述，控制在约 200~300 字以内，不够就原样，不要故意堆字数。
4. content: 原文全文，保持原始文本不改动。

输出要求：
- 只输出一个 JSON 对象，字段名固定为 id、title、summary、content。
- 不要输出解释文字或额外说明。

工作记录原文如下：
----------------
{raw_text}
----------------
"""

    response = run_agent_once_func(
        config_path=CONFIG_PATH,
        user_input=prompt,
        memory_policy=None,
        verbose=False,
    )

    print("--- Agent 原始输出 ---")
    print(response)

    # 尝试解析 JSON 并打印四个字段，便于快速检查
    print("--- 解析后的四字段 ---")
    # 先尝试从返回文本中提取首个 JSON 对象，兼容 ```json 代码块或前后说明文字
    raw = response or ""
    candidate = raw.strip()
    # 去掉典型的 ``` 包裹
    if candidate.startswith("```"):
        # 去掉起始 ```xxx 换行
        candidate = candidate.split("\n", 1)[-1]
    if candidate.endswith("```"):
        candidate = candidate.rsplit("```", 1)[0]
    # 基于首个 '{' 与最后一个 '}' 提取子串
    start = candidate.find("{")
    end = candidate.rfind("}")
    json_text = candidate[start : end + 1] if start != -1 and end != -1 and end > start else candidate
    try:
        obj = json.loads(json_text)
    except Exception as e:
        print(f"解析 JSON 失败: {e}")
        return

    print("id      :", obj.get("id"))
    print("title   :", obj.get("title"))
    print("summary :", obj.get("summary"))
    content = obj.get("content") or ""
    snippet = str(content).replace("\n", " ")[:80]
    print("content :", snippet, "...")

    print("=== 步骤2结束 ===")


def main() -> None:
    # 优先加载 ai-factory 根目录下的 .env（其中包含 DASHSCOPE_API_KEY 等），
    # 再导入 desktop_app 的 run_agent，确保模型调用所需的环境变量已就绪。
    try:
        from dotenv import load_dotenv  # type: ignore

        ai_factory_root = Path(__file__).resolve().parent
        load_dotenv(dotenv_path=ai_factory_root / ".env", override=False)
    except Exception:
        # .env 缺失或 python-dotenv 未安装时，直接忽略，保持与现有行为兼容。
        pass

    run_agent_once = _ensure_import_run_agent()

    # 步骤0：固定字符串回显
    _step0_testpoint_echo(run_agent_once)

    # 步骤1：自我介绍
    _step1_self_introduction(run_agent_once)

    # 步骤2：加工样例记录
    _step2_process_sample_record(run_agent_once)


if __name__ == "__main__":
    main()
