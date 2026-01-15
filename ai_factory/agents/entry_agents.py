"""v0 sample agents and pipelines for entries and business parsing.

本模块只定义接口和最小占位实现，用于：
- 自由文本输入 → 语义切块 → 写入 entries 表；
- 从 entries 解析出业务事实（例如报销/请假），后续可写入 biz.* 表。

真正的 LLM 调用与复杂逻辑可以在后续版本逐步补齐。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ai_factory.db import entries_repo


@dataclass
class ChunkResult:
    """单个语义块的最小结果结构。"""

    entry_id: str
    title: str
    content: str


def entries_chunk_agent(raw_text: str, base_meta: Dict[str, Any] | None = None) -> List[ChunkResult]:
    """将一段原始文本粗略切块并写入 entries，返回写入结果。

    v0 占位实现：
    - 目前仅按空行分段，每段生成一条 entry；
    - 调用方负责生成 entry_id（后续可改为由上层或 DB 统一生成）；
    - 暂不调用 LLM，只为打通从“输入 → entries_repo.insert_entry”的流程。
    """

    base_meta = base_meta or {}
    chunks: List[ChunkResult] = []

    # 简单按空行切块，后续可由真正 Agent 替代
    parts = [p.strip() for p in raw_text.split("\n\n") if p.strip()]

    import uuid

    for idx, part in enumerate(parts):
        entry_id = base_meta.get("entry_id_prefix", "ent_") + str(uuid.uuid4())
        title = base_meta.get("title_prefix", "块") + f"#{idx + 1}"

        record: Dict[str, Any] = {
            "entry_id": entry_id,
            "title": title,
            "content": part,
        }
        # 可选元数据透传
        record.update({k: v for k, v in base_meta.items() if k not in record})

        entries_repo.insert_entry(record)
        chunks.append(ChunkResult(entry_id=entry_id, title=title, content=part))

    return chunks


@dataclass
class BizFact:
    """从 entries 中解析出的业务事实最小结构（v0 占位）。"""

    source_entry_id: str
    fact_type: str  # 比如 "leave", "expense" 等
    payload: Dict[str, Any]


def biz_parse_agent(entry: Dict[str, Any]) -> List[BizFact]:
    """从单条 entry 解析业务事实，v0 为占位实现。

    当前仅根据 `space_type` 或简单关键字做极简分类，
    主要目的是确定接口形状与返回结构，便于后续接入真实 Agent。
    """

    entry_id = str(entry.get("entry_id"))
    content = str(entry.get("content", ""))

    facts: List[BizFact] = []

    # v0 极简判断：什么都不做时返回空列表
    if not content.strip():
        return facts

    # 示例：如果内容包含 "报销"，则认为是报销类事实（示意）
    if "报销" in content:
        facts.append(
            BizFact(
                source_entry_id=entry_id,
                fact_type="expense",
                payload={"raw_text": content},
            )
        )

    return facts
