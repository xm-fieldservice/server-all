from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Literal


NodeKind = Literal["human_form", "human_approve", "ai_agent", "system_task", "router"]


@dataclass
class WorkflowNode:
    id: str
    kind: NodeKind
    name: Optional[str] = None
    swimlane: Optional[str] = None
    role: Optional[str] = None
    agent_id: Optional[str] = None
    handler: Optional[str] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    ui: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)


WorkflowEdge = Tuple[str, str]


@dataclass
class WorkflowTemplate:
    template_id: str
    name: str
    description: Optional[str] = None
    version: int = 1
    category: Optional[str] = None
    nodes: List[WorkflowNode] = field(default_factory=list)
    edges: List[WorkflowEdge] = field(default_factory=list)
    start_node: Optional[str] = None
    end_nodes: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
