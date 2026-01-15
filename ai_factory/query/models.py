from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional, Literal, Any


Mode = Literal["node_list_hot", "node_list_query"]


@dataclass
class SceneTags:
    """场景标签结构，与三栏/五栏前端当前的六行标签一一对应。

    说明：
    - 这里不关心标签在 DB 中的具体存储方式，只表达“查询时有哪些标签被选中”。
    """

    department: List[str]
    planning: List[str]
    execution: List[str]
    common: List[str]
    status: List[str]
    rating: List[str]


@dataclass
class NodeQuery:
    """节点列表查询请求（v1：基于场景标签的节点查询）。"""

    tags: SceneTags
    time_window_days: Optional[int]
    mode: Mode
    page: int = 1
    page_size: int = 50


@dataclass
class NodeRecord:
    """节点查询返回的标准结构（供上层渲染使用）。"""

    entry_id: str
    title: Optional[str]
    tags: Dict[str, List[str]]
    created_at: Optional[str]
    updated_at: Optional[str]
    activity_score: Optional[float]
    extra: Dict[str, Any] | None = None
