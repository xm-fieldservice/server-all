"""v0 entry ingestion interface for external callers (e.g. 三栏页面).

提供一个高层函数 `entries_ingest(payload)`，将原始文本经最小规整后
写入 entries 表，并返回关键信息。

后续可以在这里挂接 TitleAgent / SummaryAgent / TaggingAgent 等，
目前仅使用简单的切块逻辑占位。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

import json
import os
import requests

from ai_factory.agents.entry_agents import ChunkResult
from ai_factory.db.entries_repo import insert_entry
from ai_factory.domain.tree_meta import TreeMeta, apply_tree_meta_to_entry

# 使用新的统一向量化策略模式
from ai_factory.vectorization import (
    get_strategy,
    VectorizationBackend,
)

# 保留标题/摘要生成函数（后续迁移到LLM策略模式）
from ai_factory.vectorize_entries_with_ollama import (
    generate_title_with_ollama,
    generate_summary_with_ollama,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
FAILED_MD_PATH = ROOT_DIR / "写库失败笔记保存文档.md"

USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "true").lower() == "true"


@dataclass
class EntryIngestionResult:
    """单次规整/写入操作的聚合结果（v0 版本）。"""

    entries: List[ChunkResult]


_SCENE_TAG_KEY_MAP = {
    "部门": "department",
    "规划": "planning",
    "执行": "execution",
    "公共": "common",
    "状态": "status",
    "评价": "rating",
}


def _extract_scene_tags_from_raw_text(raw_text: str) -> Dict[str, List[str]]:
    """从原始文本中解析系统标签行，构造 scene_tags 结构。

    期望格式示例：

        标签：部门=总部；规划=目标

    解析规则：
    - 仅处理以“标签：”或“标签:” 开头的行；
    - 使用“；”或“;”分隔多个键值对；
    - key 为中文（部门/规划/执行/公共/状态/评价），通过 _SCENE_TAG_KEY_MAP
      映射为 scene_tags 的字段；
    - value 作为字符串列表写入。
    """

    scene_tags: Dict[str, List[str]] = {v: [] for v in _SCENE_TAG_KEY_MAP.values()}

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        content: str | None = None
        if stripped.startswith("标签："):
            content = stripped[len("标签：") :]
        elif stripped.startswith("标签:"):
            content = stripped[len("标签:") :]

        if content is None:
            continue

        parts = [p.strip() for p in content.replace(";", "；").split("；") if p.strip()]
        for part in parts:
            if "=" not in part:
                continue
            key_cn, value = [s.strip() for s in part.split("=", 1)]
            if not key_cn or not value:
                continue
            mapped = _SCENE_TAG_KEY_MAP.get(key_cn)
            if not mapped:
                continue
            scene_tags.setdefault(mapped, []).append(value)

    # 去掉空列表，避免无效字段写入
    compact = {k: v for k, v in scene_tags.items() if v}
    return compact


def _build_scene_tags_from_payload(payload: Dict[str, Any], text: str) -> Dict[str, List[str]]:
    """优先使用 payload.extra_context.tags_snapshot 构造 scene_tags。

    - 若 extra_context.tags_snapshot 存在，则从中抽取 department/planning 等字段；
    - 否则退回到旧逻辑：从正文中的“标签：”行解析。
    """

    # 1) 尝试从 extra_context.tags_snapshot 读取
    extra_ctx = payload.get("extra_context") or {}
    if isinstance(extra_ctx, dict):
        tags_snapshot = extra_ctx.get("tags_snapshot") or {}
        if isinstance(tags_snapshot, dict) and tags_snapshot:
            scene_tags: Dict[str, List[str]] = {}

            # 情况 A：tags_snapshot 已经是展平的英文/中文 key
            for key in _SCENE_TAG_KEY_MAP.values():
                val = tags_snapshot.get(key)
                if not val:
                    continue
                if isinstance(val, list):
                    values = [str(x).strip() for x in val if x]
                else:
                    values = [str(val).strip()] if str(val).strip() else []
                if values:
                    scene_tags[key] = values

            for cn_key, en_key in _SCENE_TAG_KEY_MAP.items():
                val = tags_snapshot.get(cn_key)
                if not val:
                    continue
                if isinstance(val, list):
                    values = [str(x).strip() for x in val if x]
                else:
                    values = [str(val).strip()] if str(val).strip() else []
                if not values:
                    continue
                existing = scene_tags.get(en_key, [])
                seen = set(existing)
                merged: List[str] = list(existing)
                for v in values:
                    if v and v not in seen:
                        seen.add(v)
                        merged.append(v)
                scene_tags[en_key] = merged

            # 情况 B：五栏 SelectedTags 结构，内部包含 groups
            groups = tags_snapshot.get("groups") if isinstance(tags_snapshot, dict) else None
            if isinstance(groups, dict):
                # 遍历已知 key 映射，从对应分组中抽取 labels/path_labels/current_label
                for cn_key, en_key in _SCENE_TAG_KEY_MAP.items():
                    group = groups.get(cn_key) or groups.get(en_key)
                    if not isinstance(group, dict):
                        continue
                    mode = group.get("mode")
                    values: List[str] = []
                    if mode == "sequential":
                        path_labels = group.get("path_labels") or []
                        if path_labels:
                            values = [str(x).strip() for x in path_labels if x]
                        elif group.get("current_label"):
                            values = [str(group.get("current_label")).strip()]
                    else:
                        labels = group.get("labels") or []
                        values = [str(x).strip() for x in labels if x]

                    values = [v for v in values if v]
                    if not values:
                        continue

                    existing = scene_tags.get(en_key, [])
                    seen = set(existing)
                    merged: List[str] = list(existing)
                    for v in values:
                        if v and v not in seen:
                            seen.add(v)
                            merged.append(v)
                    scene_tags[en_key] = merged

            if scene_tags:
                return scene_tags

    # 2) 退回到旧逻辑：从文本中的“标签：”行解析
    return _extract_scene_tags_from_raw_text(text)


def _apply_channel_specific_scene_tags(
    scene_tags: Dict[str, List[str]], payload: Dict[str, Any]
) -> Dict[str, List[str]]:
    """根据来源通道对 scene_tags 做补充/规范化处理。

    当前规则：
    - 对 source_channel="wecom" 的 payload：
      - 若尚未设置 execution 维度，则默认 execution=["其他"]；
      - 在 scene_tags.work 中追加 "in_work" 标记，用于表示进入工作切片视图。
    """

    if not isinstance(scene_tags, dict):
        scene_tags = {}

    extra_ctx = payload.get("extra_context") or {}
    if not isinstance(extra_ctx, dict):
        return scene_tags

    channel_raw = extra_ctx.get("source_channel")
    channel = str(channel_raw).strip().lower() if channel_raw is not None else ""
    if channel != "wecom":
        return scene_tags

    # 企业微信笔记：默认视为进入部门工作切片的“其他”列
    exec_tags = scene_tags.get("execution")
    if not exec_tags:
        scene_tags["execution"] = ["其他"]

    # 使用 scene_tags.work=["in_work"] 表示导入到工作切片
    work_tags = scene_tags.get("work")
    if isinstance(work_tags, list):
        normalized = [str(v).strip() for v in work_tags if str(v).strip()]
        if "in_work" not in normalized:
            normalized.append("in_work")
        scene_tags["work"] = normalized
    else:
        scene_tags["work"] = ["in_work"]

    return scene_tags


def _apply_tree_fields(entry: Dict[str, Any], payload: Dict[str, Any]) -> None:
    """应用 payload 中的树形元数据到 entry 上。

    当前实现委托给 TreeMeta 模型，统一处理 parent_entry_id/space_type：
    - space_type: 优先使用 extra_meta.space_type，其次使用 entry 中已有的值，最后兜底为 "note"；
    - parent_entry_id: 仅在有非空字符串时写入。
    """

    meta = TreeMeta.from_payload(payload)
    apply_tree_meta_to_entry(entry, meta)


def _append_failed_entry_to_md(raw_text: str, payload: Dict[str, Any], error: BaseException) -> None:
    """将写库失败的原始笔记追加到统一的失败文档中。

    - 使用与正常工作笔记相同的 header 形态，方便后续用补入脚本处理。
    - 不抛出异常，任何文件写入错误都只打印到 stderr。
    """

    try:
        note_dt = str(payload.get("note_datetime") or "").strip()
        if not note_dt:
            # 若无显式 note_datetime，则用当前 UTC 时间，避免 header 为空
            note_dt = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        lines: List[str] = []
        # 与正常工作笔记保持完全一致的形态：
        #   ## 📝 笔记 - <时间>
        #   <raw_text>
        #   <空行分隔>
        lines.append(f"## 📝 笔记 - {note_dt}\n\n")
        lines.append(raw_text.rstrip("\n") + "\n\n")

        FAILED_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FAILED_MD_PATH.open("a", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as file_err:  # noqa: BLE001
        print(f"[entries_ingest] 写入失败文档时出错: {file_err!r}")


def _vectorize_entry_sync(entry: Dict[str, Any], context: str = "entries_ingest") -> bool:
    """同步向量化 entry 并写入 embeddings 表。

    统一封装向量化逻辑，使用策略模式。被多处调用：
    - 长文本切块后的第一个 chunk
    - 中等长度文本的完整 entry
    - 异步任务兜底流程

    Args:
        entry: 已插入 entries 表的 entry dict
        context: 调用上下文标识，用于日志区分

    Returns:
        bool: 是否成功完成向量化
    """
    try:
        # 使用策略模式获取默认向量化策略 (DashScope)
        strategy = get_strategy()
        success = strategy.process_entry(entry)
        if success:
            print(f"[{context}] 使用DashScope向量化完成 (1024维)")
        return success
    except Exception as exc:  # noqa: BLE001
        print(f"[{context}] 同步向量化失败，将由异步脚本补齐: {exc!r}")
        return False


def entries_ingest(payload: Dict[str, Any], *, use_remote_embedding: bool = False) -> Dict[str, Any]:
    """高层入口：处理原始输入并写入 entries.
    
    Args:
        payload: 任务参数
        use_remote_embedding: 是否使用远端API(DeePSeek)进行向量化，默认为False使用本地Ollama
                             2号通道(异步任务)应设置为True以使用云端向量化服务

    支持两种场景：
    1. 笔记入库：input_content = 笔记原文，answer_payload = null
    2. 问答场景（RAG/Web）：input_content = 用户提问，answer_payload = LLM答案（Markdown）

    期望 payload 结构（v0 草案）：
    - raw_text: str（笔记场景必填，问答场景为null）
    - input_content: str（问答场景必填，笔记场景可选，默认使用raw_text）
    - answer_payload: str（问答场景必填，笔记场景为null）
    - project_code: Optional[str]
    - user_id: Optional[str]
    - note_datetime: Optional[str]
    - extra_context: dict（可选）

    返回值为 JSON 友好的 dict，便于后续直接挂到 HTTP API 上.
    """

    raw_text = str(payload.get("raw_text", "")).strip()
    input_content = str(payload.get("input_content", "")).strip()
    answer_payload_raw = payload.get("answer_payload")  # 可能是str或None

    # 确定场景和最终使用的输入内容
    # 笔记场景：raw_text有实际内容，answer_payload为None
    # 问答场景：input_content有实际内容，answer_payload有实际内容，raw_text为空
    is_note_scenario = bool(raw_text) and (answer_payload_raw is None)
    is_qa_scenario = bool(input_content) and (answer_payload_raw is not None)

    answer_payload = answer_payload_raw  # 用于entry字段

    # 确定最终使用的输入内容
    if is_note_scenario:
        # 笔记场景：使用raw_text
        final_content = raw_text
    elif is_qa_scenario:
        # 问答场景：使用input_content
        final_content = input_content
    else:
        # 没有指定场景，尝试用raw_text
        final_content = raw_text if raw_text else input_content

    if not final_content:
        raise ValueError("payload.raw_text 或 payload.input_content 不能为空")

    text_len = len(raw_text)

    # 三档规则：
    # 1) ≤60 字：完全不用 LLM，title = 原文，summary = 原文；
    # 2) 60~600 字：summary 仍用原文，但通过 LLM 只生成一个不超过 ~60 字且不虚构的新标题；
    # 3) >600 字：保持原有长文本提示词逻辑（title+summary 由 LLM 生成）。

    # 确定场景：笔记还是问答
    is_note_scenario = bool(raw_text) and not bool(answer_payload)

    if text_len <= 60:
        base_meta: Dict[str, Any] = {}
        for key in ("project_code", "user_id", "note_datetime"):
            if key in payload:
                base_meta[key] = payload[key]

        extra_ctx = payload.get("extra_context") or {}
        if isinstance(extra_ctx, dict):
            base_meta.update(extra_ctx)

        entry_id = f"ent_{uuid4().hex[:8]}"
        title = final_content
        summary = final_content
        created_at = datetime.utcnow().isoformat()

        entry: Dict[str, Any] = {
            "entry_id": entry_id,
            "title": title,
            "summary_ai": summary,
            "input_content": final_content,
            "answer_payload": None if is_note_scenario else answer_payload,
            "created_at": created_at,
        }

        # 优先从 payload.extra_context.tags_snapshot 构造 scene_tags, 退回到从正文解析
        scene_tags = _build_scene_tags_from_payload(payload, raw_text)
        scene_tags = _apply_channel_specific_scene_tags(scene_tags, payload)
        if scene_tags:
            entry["scene_tags"] = scene_tags

        if "project_code" in base_meta:
            entry["project_code"] = base_meta["project_code"]
        if "user_id" in base_meta:
            entry["user_id"] = base_meta["user_id"]

        try:
            _apply_tree_fields(entry, payload)
        except Exception as exc:  # noqa: BLE001
            print(f"[entries_ingest] 忽略 tree 字段错误，使用默认 note: {exc!r}")
            entry.setdefault("space_type", "note")
            entry.pop("parent_entry_id", None)

        insert_entry(entry)
        _vectorize_entry_sync(entry, context="entries_ingest")

        chunk = ChunkResult(entry_id=entry_id, title=title, content=raw_text)
        result = EntryIngestionResult(entries=[chunk])

        return {
            "entries": [asdict(c) for c in result.entries],
        }

    if text_len <= 600:
        # 只让 LLM 帮忙压缩出一个不虚构的标题，summary 直接用原文。
        base_meta: Dict[str, Any] = {}
        for key in ("project_code", "user_id", "note_datetime"):
            if key in payload:
                base_meta[key] = payload[key]

        extra_ctx = payload.get("extra_context") or {}
        if isinstance(extra_ctx, dict):
            base_meta.update(extra_ctx)

        created_at = datetime.utcnow().isoformat()

        if USE_LOCAL_LLM:
            try:
                title = generate_title_with_ollama(final_content, max_length=60)
                if not title:
                    title = final_content[:60]
                print(f"[entries_ingest] 使用本地Ollama生成标题: {title[:30]}...")
            except Exception as e:
                print(f"[entries_ingest] 本地Ollama调用失败，回退到原文: {e}")
                title = final_content[:60]
        else:
            # 使用DeepSeek API
            model_name = os.getenv("INGEST_MODEL_NAME", "deepseek-chat")
            base_url = os.getenv("INGEST_MODEL_BASE_URL", "https://api.deepseek.com").rstrip("/")
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError("DEEPSEEK_API_KEY 未设置，无法调用 deepseek-chat API")

            prompt = f"""
下面是一条较短的工作记录，请你只生成一个 JSON 对象用于"标题压缩"：

字段要求：
1. title: 基于原文内容，生成一个简洁清晰的中文标题，长度不超过约 60 个中文字符；\
   - 只允许使用原文中已经出现或可以直接概括出来的信息，不要凭空添加新的背景、项目名、技术方案或结论；\
   - 标题可以对原文进行适度归纳和压缩，但不得引入原文中没有提到的具体人物、系统名称或实现细节。

输出要求：
- 只输出一个 JSON 对象，字段名固定为 title；
- 不要输出 summary 字段，也不要输出其他解释文字。

工作记录原文如下：
----------------
{final_content}
----------------
"""

            try:
                http_resp = requests.post(
                    f"{base_url}/v1/chat/completions",
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=600,
                )
                http_resp.raise_for_status()
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"调用 deepseek-chat 失败: {e}") from e

            try:
                data = http_resp.json()
            except JSONDecodeError as e:  # noqa: BLE001
                raise RuntimeError(
                    f"解析 deepseek-chat 返回 JSON 失败: {e}; text={http_resp.text[:500]}"
                ) from e

            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError("deepseek-chat 返回结果中不包含 choices 字段")

            message = (choices[0] or {}).get("message") or {}
            text = str(message.get("content") or "")

            candidate = text.strip()
            if candidate.startswith("```"):
                candidate = candidate.split("\n", 1)[-1]
            if candidate.endswith("```"):
                candidate = candidate.rsplit("```", 1)[0]
            start = candidate.find("{")
            end = candidate.rfind("}")
            json_text = (
                candidate[start : end + 1]
                if start != -1 and end != -1 and end > start
                else candidate
            )

            try:
                obj = json.loads(json_text)
                title = str(obj.get("title") or "").strip()
                if not title:
                    title = final_content[:60]
            except Exception as e:
                print(
                    f"[entries_ingest] LLM 标题 JSON 解析失败, 回退到原文: {e}; "
                    f"raw_output={final_content[:200]!r}"
                )
                title = final_content[:60]

        summary = final_content

        entry_id = f"ent_{uuid4().hex[:8]}"
        created_at = datetime.utcnow().isoformat()

        entry: Dict[str, Any] = {
            "entry_id": entry_id,
            "title": title,
            "summary_ai": summary,
            "input_content": final_content,
            "answer_payload": None if is_note_scenario else answer_payload,
            "created_at": created_at,
        }

        # 优先从 payload.extra_context.tags_snapshot 构造 scene_tags, 退回到从正文解析
        scene_tags = _build_scene_tags_from_payload(payload, final_content)
        scene_tags = _apply_channel_specific_scene_tags(scene_tags, payload)
        if scene_tags:
            entry["scene_tags"] = scene_tags

        if "project_code" in base_meta:
            entry["project_code"] = base_meta["project_code"]
        if "user_id" in base_meta:
            entry["user_id"] = base_meta["user_id"]

        try:
            _apply_tree_fields(entry, payload)
        except Exception as exc:  # noqa: BLE001
            print(f"[entries_ingest] : {exc!r}")
            entry.setdefault("space_type", "note")
            entry.pop("parent_entry_id", None)

        insert_entry(entry)
        _vectorize_entry_sync(entry, context="entries_ingest")

        chunk = ChunkResult(entry_id=entry_id, title=title, content=raw_text)
        result = EntryIngestionResult(entries=[chunk])

        return {
            "entries": [asdict(c) for c in result.entries],
        }

    try:
        base_meta: Dict[str, Any] = {}
        for key in ("project_code", "user_id", "note_datetime"):
            if key in payload:
                base_meta[key] = payload[key]

        extra_ctx = payload.get("extra_context") or {}
        if isinstance(extra_ctx, dict):
            base_meta.update(extra_ctx)

        if USE_LOCAL_LLM:
            try:
                title = generate_title_with_ollama(final_content, max_length=60)
                summary = generate_summary_with_ollama(final_content, max_length=500)
                print(f"[entries_ingest] 使用本地Ollama生成: title={title[:30]}..., summary={summary[:50]}...")
            except Exception as e:
                print(f"[entries_ingest] 本地Ollama调用失败，回退到原文: {e}")
                title = final_content[:60]
                summary = final_content
        else:
            # 使用DeepSeek API
            model_name = os.getenv("INGEST_MODEL_NAME", "deepseek-chat")
            base_url = os.getenv("INGEST_MODEL_BASE_URL", "https://api.deepseek.com").rstrip("/")
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError("DEEPSEEK_API_KEY , deepseek-chat API")

            prompt = f"""
下面是一条较长的工作记录，请你帮我做结构化的标题和摘要总结，输出为 JSON：

字段要求：
1. title: 基于原文内容生成一个简洁清晰的中文标题，推荐长度 20~40 个中文字符，上限约 60 个中文字符；
   - 只能使用原文中已经出现或可以直接概括出来的信息，不要凭空添加新的背景、项目名、技术方案或结论；
   - 可以适度归纳和压缩，但不得引入原文中没有提到的具体人物、系统名称或实现细节。
2. summary: 对原文进行较完整的中文总结，使用 Markdown 段落形式，推荐长度 300~600 字；
   - 重点保留原文中的关键决策、问题、方案和 TODO；
   - 不要加入原文没有明确表达过的推测性结论。

输出要求：
- 只输出一个 JSON 对象，字段名固定为 title 和 summary；
- 不要输出任何额外的解释文字、前后缀或代码块标记（例如 ```json）。

工作记录原文如下：
----------------
{raw_text}
----------------
"""

            try:
                http_resp = requests.post(
                    f"{base_url}/v1/chat/completions",
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=600,
                )
                http_resp.raise_for_status()
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"deepseek-chat : {e}") from e

            try:
                data = http_resp.json()
            except JSONDecodeError as e:  # noqa: BLE001
                raise RuntimeError(
                    f"deepseek-chat JSON : {e}; text={http_resp.text[:500]}"
                ) from e

            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError("deepseek-chat : choices ")

            message = (choices[0] or {}).get("message") or {}
            text = str(message.get("content") or "")

            candidate = text.strip()
            if candidate.startswith("```"):
                candidate = candidate.split("\n", 1)[-1]
            if candidate.endswith("```"):
                candidate = candidate.rsplit("```", 1)[0]
            start = candidate.find("{")
            end = candidate.rfind("}")
            json_text = (
                candidate[start : end + 1]
                if start != -1 and end != -1 and end > start
                else candidate
            )

            try:
                obj = json.loads(json_text)
                title = str(obj.get("title") or "").strip()
                summary = str(obj.get("summary") or "").strip()
            except Exception as e:
                print(
                    f"[entries_ingest] LLM JSON 解析失败, 回退到原文: {e}; "
                    f"raw_output={final_content[:200]!r}"
                )
                title = final_content[:60]
                summary = final_content

        if not title:
            title = final_content[:60]
        if not summary:
            summary = final_content

        entry_id = f"ent_{uuid4().hex[:8]}"
        content = final_content  # 长文本场景使用final_content
        created_at = datetime.utcnow().isoformat()

        entry: Dict[str, Any] = {
            "entry_id": entry_id,
            "title": title,
            "summary_ai": summary,
            "input_content": content,
            "answer_payload": None if is_note_scenario else answer_payload,
            "created_at": created_at,
        }

        # 优先从 payload.extra_context.tags_snapshot 构造 scene_tags, 退回到从正文解析
        scene_tags = _build_scene_tags_from_payload(payload, content)
        scene_tags = _apply_channel_specific_scene_tags(scene_tags, payload)
        if scene_tags:
            entry["scene_tags"] = scene_tags

        if "project_code" in base_meta:
            entry["project_code"] = base_meta["project_code"]
        if "user_id" in base_meta:
            entry["user_id"] = base_meta["user_id"]

        try:
            _apply_tree_fields(entry, payload)
        except Exception as exc:  # noqa: BLE001
            print(f"[entries_ingest] : {exc!r}")
            entry.setdefault("space_type", "note")
            entry.pop("parent_entry_id", None)

        insert_entry(entry)
        _vectorize_entry_sync(entry, context="entries_ingest")

        chunk = ChunkResult(entry_id=entry_id, title=title, content=content)
        result = EntryIngestionResult(entries=[chunk])

        return {
            "entries": [asdict(c) for c in result.entries],
        }
    except Exception as e:  # noqa: BLE001
        _append_failed_entry_to_md(raw_text, payload, e)
        raise
