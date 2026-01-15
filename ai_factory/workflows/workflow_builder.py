from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from .workflow_config import WorkflowTemplate


@dataclass
class CompiledWorkflow:
    """基础编译结果结构。

    在尚未接入 LangGraph 之前，先提供一个轻量级的中间表示：
    - 保留原始 WorkflowTemplate；
    - 提供邻接表 / 反向邻接表，便于后续执行器或可视化使用；
    - 确保模板在结构上是自洽的（节点/边/起止节点合法）。
    """

    template: WorkflowTemplate
    adjacency: Dict[str, List[str]] = field(default_factory=dict)
    reverse_adjacency: Dict[str, List[str]] = field(default_factory=dict)


def build_graph_from_config(template: WorkflowTemplate) -> CompiledWorkflow:
    """对 WorkflowTemplate 做结构校验，并构建基础邻接表表示。

    后续接入 LangGraph 时，可以在此函数内部将 CompiledWorkflow
    映射为具体的 Graph / StateGraph；对调用方来说，签名保持稳定。
    """

    # 基本校验
    if not template.nodes:
        raise ValueError("WorkflowTemplate must define at least one node.")

    if not template.start_node:
        raise ValueError("WorkflowTemplate.start_node must be set.")

    # 收集节点 ID
    node_ids: Set[str] = set()
    for node in template.nodes:
        if node.id in node_ids:
            raise ValueError(f"Duplicate node id detected in template '{template.template_id}': {node.id}")
        node_ids.add(node.id)

    # 起始/结束节点合法性
    if template.start_node not in node_ids:
        raise ValueError(
            f"start_node '{template.start_node}' is not defined in nodes of template '{template.template_id}'",
        )

    for end_id in template.end_nodes:
        if end_id not in node_ids:
            raise ValueError(
                f"end_node '{end_id}' is not defined in nodes of template '{template.template_id}'",
            )

    # 构建邻接表
    adjacency: Dict[str, List[str]] = {nid: [] for nid in node_ids}
    reverse_adjacency: Dict[str, List[str]] = {nid: [] for nid in node_ids}

    for src, dst in template.edges:
        if src not in node_ids:
            raise ValueError(
                f"edge source '{src}' is not defined in nodes of template '{template.template_id}'",
            )
        if dst not in node_ids:
            raise ValueError(
                f"edge target '{dst}' is not defined in nodes of template '{template.template_id}'",
            )

        adjacency[src].append(dst)
        reverse_adjacency[dst].append(src)

    # 可选：检测从 start_node 可达性，避免悬空节点
    visited: Set[str] = set()
    stack: List[str] = [template.start_node]

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        stack.extend(adjacency.get(current, []))

    unreachable = node_ids - visited
    if unreachable:
        raise ValueError(
            f"template '{template.template_id}' has unreachable nodes from start_node '{template.start_node}': "
            f"{sorted(unreachable)}",
        )

    return CompiledWorkflow(template=template, adjacency=adjacency, reverse_adjacency=reverse_adjacency)
