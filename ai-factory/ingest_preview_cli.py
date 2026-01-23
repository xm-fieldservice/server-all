from __future__ import annotations

import json
import sys
from pathlib import Path


CONFIG_PATH = r"D:\AI\desktop_app\config\agents\ingest_agent.json"
DESKTOP_APP_ROOT = Path(r"D:\AI\desktop_app")


def _ensure_import_run_agent():
    config_dir = DESKTOP_APP_ROOT / "config"
    if str(config_dir) not in sys.path:
        sys.path.insert(0, str(config_dir))

    import run_agent  # type: ignore
    return run_agent.run_agent_once


def _build_prompt(raw_text: str) -> str:
    return f"""
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


def _extract_json_object(text: str) -> str:
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1]
    if candidate.endswith("```"):
        candidate = candidate.rsplit("```", 1)[0]
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        return candidate[start : end + 1]
    return candidate


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python ingest_preview_cli.py <工作记录文件路径>")
        sys.exit(1)

    record_path = Path(sys.argv[1])
    if not record_path.exists():
        print(f"文件不存在: {record_path}")
        sys.exit(1)

    try:
        from dotenv import load_dotenv  # type: ignore

        current = Path(__file__).resolve()
        project_root = current.parent          # .../ai-factory
        ai_root = project_root.parent          # .../AI

        # 1) 全局 D:\AI\.env
        global_env = ai_root / ".env"
        if global_env.is_file():
            load_dotenv(global_env, override=False)

        # 2) 项目级 D:\AI\ai-factory\.env（可选覆盖）
        local_env = project_root / ".env"
        if local_env.is_file():
            load_dotenv(local_env, override=True)
    except Exception:
        pass

    run_agent_once = _ensure_import_run_agent()

    raw_text = record_path.read_text(encoding="utf-8")
    prompt = _build_prompt(raw_text)

    response = run_agent_once(
        config_path=CONFIG_PATH,
        user_input=prompt,
        memory_policy=None,
        verbose=False,
    )

    json_text = _extract_json_object(response or "")

    try:
        obj = json.loads(json_text)
    except Exception as e:
        print("原始模型输出:")
        print(response)
        print("\n解析 JSON 失败:", e)
        sys.exit(1)

    print("id      :", obj.get("id"))
    print("title   :", obj.get("title"))
    print("summary :", obj.get("summary"))
    content = obj.get("content") or ""
    snippet = str(content).replace("\n", " ")[:120]
    print("content :", snippet, "...")


if __name__ == "__main__":
    main()
