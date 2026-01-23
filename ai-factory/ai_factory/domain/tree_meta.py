from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class TreeMeta:
    """entries 树形/规划相关的元数据视图。

    - parent_entry_id: 树形父节点 ID；
    - space_type: 规划/节点类型（如 strategy/goal/plan/project/note 等）。
    """

    parent_entry_id: Optional[str] = None
    space_type: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "TreeMeta":
        """从 entries_ingest 的 payload 中提取树形元数据字段。

        当前仅关注 payload["extra_meta"] 中的 parent_entry_id / space_type，
        其余字段由调用方自行处理。
        """

        extra_meta = payload.get("extra_meta") or {}
        if not isinstance(extra_meta, dict):
            extra_meta = {}

        parent_entry_id_val = extra_meta.get("parent_entry_id")
        parent_entry_id: Optional[str]
        if parent_entry_id_val is None:
            parent_entry_id = None
        else:
            s = str(parent_entry_id_val).strip()
            parent_entry_id = s or None

        space_type_val = extra_meta.get("space_type")
        space_type: Optional[str]
        if space_type_val is None:
            space_type = None
        else:
            s = str(space_type_val).strip()
            space_type = s or None

        return cls(parent_entry_id=parent_entry_id, space_type=space_type)


def apply_tree_meta_to_entry(entry: Dict[str, Any], meta: TreeMeta) -> None:
    """将 TreeMeta 信息应用到 entries 行字典上。

    - 若 meta.space_type 为空，则保证 entry.space_type 至少为 "note"；
    - 仅在 parent_entry_id 非空字符串时写入该字段。
    """

    # space_type：允许调用方预先在 entry 中设置，TreeMeta 只做补充/覆盖
    space_type = meta.space_type or entry.get("space_type")
    if space_type:
        entry["space_type"] = str(space_type)
    else:
        entry.setdefault("space_type", "note")

    # parent_entry_id：只有在有非空值时才写入，避免无意义字段
    if meta.parent_entry_id is not None:
        s = str(meta.parent_entry_id).strip()
        if s:
            entry["parent_entry_id"] = s
