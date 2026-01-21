from __future__ import annotations

"""对比调试脚本：qa_answer_rag（v1） vs qa_answer_rag_v2（流水线版）。

用法（在 ai-factory 根目录下）：

    python debug_rag_answer_v2.py

脚本会：
- 使用同一个 question payload；
- 分别调用 v1/v2 接口；
- 打印问题、回答、citations 数量，以及 v2 的 _intent/_sources；
便于观察新流水线与现有实现的差异与数据结构。
"""

import json
from pathlib import Path
from typing import Any, Dict


def _load_dotenv_if_available() -> None:
    """统一加载全局 D:\AI\.env 和项目级 .env（如果存在）。"""

    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    current = Path(__file__).resolve()
    project_root = current.parent      # .../ai-factory
    ai_root = project_root.parent      # .../AI

    # 1) 全局 D:\AI\.env
    global_env = ai_root / ".env"
    if global_env.is_file():
        load_dotenv(global_env, override=False)

    # 2) 项目级 D:\AI\ai-factory\.env（可选覆盖）
    local_env = project_root / ".env"
    if local_env.is_file():
        load_dotenv(local_env, override=True)


def _print_section(title: str) -> None:
    print("\n" + "=" * 8, title, "=" * 8)


def _short_answer_preview(text: Any, length: int = 200) -> str:
    s = str(text or "").strip().replace("\n", " ")
    if len(s) <= length:
        return s
    return s[:length] + "..."


def main() -> None:
    _load_dotenv_if_available()

    from ai_factory.integrations.rag_pipeline_api_v2 import qa_answer_rag_v2

    question_text = (
        "我们在12-14日的所有工作记录中，你梳理一下，我们连续的工作记录中，切换了几个主题，"
        "每次切换是跳跃式的，还是与前面的主题有关，描述一下这种关系。"
    )

    payload: Dict[str, Any] = {
        "question_text": question_text,
        # 如有需要可限定 project_code / user_id
        # "project_code": "demo_project",
        # "user_id": "u_demo",
        "top_k": 10,
    }

    _print_section("调用 qa_answer_rag_v2 (pipeline)")
    result_v2 = qa_answer_rag_v2(dict(payload))
    print("[question]", result_v2.get("question"))
    answer_v2 = result_v2.get("answer")
    print("[answer.preview]", _short_answer_preview(answer_v2))
    citations_v2 = result_v2.get("citations") or []
    print("[citations.count]", len(citations_v2))
    print("\n[v2.answer.full]\n", str(answer_v2 or "").strip())

    # 将完整结果写入 Markdown 文档，避免终端截断
    try:
        project_root = Path(__file__).resolve().parent
        out_path = project_root / "debug_rag_answer_v2_output.md"
        intent_v2 = result_v2.get("_intent") or {}
        structure_v2 = result_v2.get("_structure") or {}

        lines = []
        lines.append("# RAG v2 调试输出\n")
        lines.append("## 公共信息\n")
        lines.append(f"**question:** {question_text}\n")
        lines.append("")

        lines.append("## v2：qa_answer_rag_v2 (pipeline)\n")
        lines.append(f"- citations.count: {len(citations_v2)}\n")
        lines.append("### v2.intent (摘要)\n")
        lines.append("```json")
        lines.append(json.dumps(intent_v2, ensure_ascii=False, indent=2))
        lines.append("```\n")

        lines.append("### v2.structure\n")
        lines.append("```json")
        lines.append(json.dumps(structure_v2, ensure_ascii=False, indent=2))
        lines.append("```\n")

        lines.append("### v2.answer\n")
        lines.append(str(answer_v2 or "").strip() + "\n")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n[debug] 已写入输出文件: {out_path}")
    except Exception as exc:  # noqa: BLE001
        print("[debug] 写入 debug_rag_answer_v2_output.md 失败:", exc)


if __name__ == "__main__":
    main()
