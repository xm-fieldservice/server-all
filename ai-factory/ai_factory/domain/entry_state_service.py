from __future__ import annotations

from typing import Any, Dict, Optional

from ai_factory.db.entries_repo import get_entry, update_entry_fields


def move_to_planning_lane(entry_id: str, planning_lane: str, parent_entry_id: Optional[str] = None) -> None:
    """更新指定 entry 的规划相关元数据（scene_tags.planning / space_type / parent_entry_id）。

    - 不修改标题、正文、summary 或 embedding；
    - 仅在记录存在时生效，找不到 entry 时静默返回。
    """

    entry_id = (entry_id or "").strip()
    planning_lane = (planning_lane or "").strip()
    if not entry_id:
        return

    entry = get_entry(entry_id)
    if not entry:
        return

    fields: Dict[str, Any] = {}

    # 更新 scene_tags.planning
    scene_tags = entry.get("scene_tags") or {}
    if not isinstance(scene_tags, dict):
        scene_tags = {}
    if planning_lane:
        scene_tags["planning"] = [planning_lane]
        fields["scene_tags"] = scene_tags

    # 根据规划维度简单推导 space_type（占位规则，可后续细化）
    space_type_map = {
        "战略": "strategy",
        "目标": "goal",
        "计划": "plan",
        "项目": "project",
    }
    space_type = space_type_map.get(planning_lane)
    if space_type:
        fields["space_type"] = space_type

    # 更新 parent_entry_id（如提供）
    if parent_entry_id is not None:
        s = str(parent_entry_id).strip()
        if s:
            fields["parent_entry_id"] = s
        else:
            # 空字符串视为清空父节点
            fields["parent_entry_id"] = None

    if fields:
        update_entry_fields(entry_id, fields)


def move_to_execution_lane(
    entry_id: str,
    execution_lane: Optional[str],
    import_to_work: Optional[bool] = None,
    parent_entry_id: Optional[str] = None,
) -> None:
    """更新指定 entry 的执行维度元数据（scene_tags.execution / parent_entry_id 等）。

    - 不修改标题、正文、summary 或 embedding；
    - 仅在记录存在时生效，找不到 entry 时静默返回；
    - execution_lane 仅允许为执行维度预设枚举之一或 None。
    """

    entry_id = (entry_id or "").strip()
    if not entry_id:
        return

    # 执行维度允许值约定：任务/议题/笔记/日程/其他
    allowed_lanes = {"任务", "议题", "笔记", "日程", "其他"}
    lane: Optional[str]
    if execution_lane is None:
        lane = None
    else:
        s = str(execution_lane).strip()
        lane = s or None
        if lane is not None and lane not in allowed_lanes:
            # 非法值直接忽略本次更新请求
            return

    entry = get_entry(entry_id)
    if not entry:
        return

    fields: Dict[str, Any] = {}

    # 更新 scene_tags.execution
    scene_tags = entry.get("scene_tags") or {}
    if not isinstance(scene_tags, dict):
        scene_tags = {}
    if lane is None:
        # 视为清空执行维度标签
        if "execution" in scene_tags:
            scene_tags.pop("execution", None)
            fields["scene_tags"] = scene_tags
    else:
        scene_tags["execution"] = [lane]
        fields["scene_tags"] = scene_tags

    # 预留 import_to_work 标记：当前方案使用 scene_tags.work 简单表示
    if import_to_work is not None:
        work_tags = scene_tags.get("work") if isinstance(scene_tags.get("work"), list) else []
        if import_to_work:
            # 标记为在工作切片中
            if "in_work" not in work_tags:
                work_tags = list(work_tags) + ["in_work"]
            scene_tags["work"] = work_tags
        else:
            # 退出工作切片：移除标记
            if work_tags:
                work_tags = [v for v in work_tags if v != "in_work"]
                if work_tags:
                    scene_tags["work"] = work_tags
                else:
                    scene_tags.pop("work", None)
        fields["scene_tags"] = scene_tags

    # 更新 parent_entry_id（如提供）
    if parent_entry_id is not None:
        s = str(parent_entry_id).strip()
        if s:
            fields["parent_entry_id"] = s
        else:
            fields["parent_entry_id"] = None

    if fields:
        update_entry_fields(entry_id, fields)


def set_parent(entry_id: str, parent_entry_id: Optional[str]) -> None:
    """仅更新 parent_entry_id。"""

    entry_id = (entry_id or "").strip()
    if not entry_id:
        return

    entry = get_entry(entry_id)
    if not entry:
        return

    if parent_entry_id is None:
        fields = {"parent_entry_id": None}
    else:
        s = str(parent_entry_id).strip()
        fields = {"parent_entry_id": s or None}

    update_entry_fields(entry_id, fields)


def set_status(entry_id: str, status: str) -> None:
    """更新 entries.status 等状态类元数据字段。"""

    entry_id = (entry_id or "").strip()
    status = (status or "").strip()
    if not entry_id or not status:
        return

    entry = get_entry(entry_id)
    if not entry:
        return

    update_entry_fields(entry_id, {"status": status})


def set_favorite(entry_id: str, favorite: bool) -> None:
    entry_id = (entry_id or "").strip()
    if not entry_id:
        return

    entry = get_entry(entry_id)
    if not entry:
        return

    scene_tags = entry.get("scene_tags") or {}
    if not isinstance(scene_tags, dict):
        scene_tags = {}

    flags = scene_tags.get("flags")
    if not isinstance(flags, list):
        flags = []

    if favorite:
        if "favorite" not in flags:
            flags = list(flags) + ["favorite"]
    else:
        if flags:
            flags = [v for v in flags if v != "favorite"]

    if flags:
        scene_tags["flags"] = flags
    else:
        if "flags" in scene_tags:
            scene_tags.pop("flags", None)

    update_entry_fields(entry_id, {"scene_tags": scene_tags})
