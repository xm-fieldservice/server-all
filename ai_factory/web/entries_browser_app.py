from __future__ import annotations

"""简单的 entries 调试浏览页面（FastAPI 版）。

功能目标：
- 直接连当前 Postgres（复用 ai_factory.db.pgvector_client 配置）。
- 左右两栏：左侧为列表+查询，右侧为单条记录详情。
- 展示 entries 表的所有主要字段：entry_id/title/summary_ai/content/project_code/user_id/created_at。
- 提供：
  - 文本查询框（在 title/summary_ai/content 上做 ILIKE 搜索）；
  - 分页（上一页/下一页）；
  - 在当前结果集中“上一条 / 下一条”浏览；
  - 右侧一个大的只读文本框浏览原文 content。

运行方式（示例）：

  pip install fastapi "uvicorn[standard]" psycopg2-binary
  
  # 确保 AI_PG_HOST / AI_PG_PORT / AI_PG_DB / AI_PG_USER / AI_PG_PASSWORD 已配置
  
  uvicorn ai_factory.web.entries_browser_app:app --reload --port 8001

然后在浏览器打开：http://localhost:8001
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from fastapi import FastAPI, Query, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from ai_factory.db.pgvector_client import connection_scope
from ai_factory.integrations.entries_ingest import entries_ingest


PAGE_SIZE = 50


@dataclass
class EntryRow:
    entry_id: str
    title: str
    summary_ai: Optional[str]
    content: str
    project_code: Optional[str]
    user_id: Optional[str]
    # 元数据字段：便于在 DB 浏览器中调试父子关系与空间类型
    space_type: Optional[str]
    parent_entry_id: Optional[str]
    scene_tags_json: Optional[str]
    created_at: str


def _list_entries(
    q: Optional[str], *, page: int, page_size: int = PAGE_SIZE
) -> List[EntryRow]:
    """按时间倒序列出 entries，支持简单模糊搜索和分页。"""

    offset = (page - 1) * page_size

    if q:
        sql = (
            "SELECT entry_id, title, summary_ai, content, project_code, user_id, "
            "space_type, parent_entry_id, scene_tags::text AS scene_tags_json, "
            "to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at "
            "FROM entries "
            "WHERE title ILIKE %s OR summary_ai ILIKE %s OR content ILIKE %s "
            "ORDER BY created_at DESC, entry_id DESC "
            "LIMIT %s OFFSET %s"
        )
        pattern = f"%{q}%"
        params = (pattern, pattern, pattern, page_size, offset)
    else:
        sql = (
            "SELECT entry_id, title, summary_ai, content, project_code, user_id, "
            "space_type, parent_entry_id, scene_tags::text AS scene_tags_json, "
            "to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at "
            "FROM entries "
            "ORDER BY created_at DESC, entry_id DESC "
            "LIMIT %s OFFSET %s"
        )
        params = (page_size, offset)

    rows: List[EntryRow] = []
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for (
                entry_id,
                title,
                summary_ai,
                content,
                project_code,
                user_id,
                space_type,
                parent_entry_id,
                scene_tags_json,
                created_at,
            ) in cur.fetchall():
                rows.append(
                    EntryRow(
                        entry_id=str(entry_id),
                        title=title or "",
                        summary_ai=summary_ai,
                        content=content or "",
                        project_code=project_code,
                        user_id=user_id,
                        space_type=space_type,
                        parent_entry_id=parent_entry_id,
                        scene_tags_json=scene_tags_json,
                        created_at=created_at,
                    )
                )
    return rows


def _get_entry(entry_id: str) -> Optional[EntryRow]:
    sql = (
        "SELECT entry_id, title, summary_ai, content, project_code, user_id, "
        "space_type, parent_entry_id, scene_tags::text AS scene_tags_json, "
        "to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at "
        "FROM entries WHERE entry_id = %s"
    )
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (entry_id,))
            row = cur.fetchone()
            if not row:
                return None
            (
                entry_id,
                title,
                summary_ai,
                content,
                project_code,
                user_id,
                space_type,
                parent_entry_id,
                scene_tags_json,
                created_at,
            ) = row
    return EntryRow(
        entry_id=str(entry_id),
        title=title or "",
        summary_ai=summary_ai,
        content=content or "",
        project_code=project_code,
        user_id=user_id,
        space_type=space_type,
        parent_entry_id=parent_entry_id,
        scene_tags_json=scene_tags_json,
        created_at=created_at,
    )


def _delete_entry(entry_id: str) -> None:
    """删除单条 entry 记录（仅用于本地调试页面）。"""
    # 为避免外键约束错误，这里先删除 entry_embeddings 中关联记录，再删除 entries 本身。

    sql_delete_embedding = "DELETE FROM entry_embeddings WHERE entry_id = %s"
    sql_delete_entry = "DELETE FROM entries WHERE entry_id = %s"
    with connection_scope() as conn:
        with conn.cursor() as cur:
            # 1) 删除向量表中的关联记录（如果没有匹配行，影响行数为 0 也没关系）
            cur.execute(sql_delete_embedding, (entry_id,))
            # 2) 删除 entries 主表记录
            cur.execute(sql_delete_entry, (entry_id,))


def _build_url(base: str, **params: Any) -> str:
    clean_params: Dict[str, Any] = {}
    for k, v in params.items():
        if v is None or v == "":
            continue
        clean_params[k] = v
    if not clean_params:
        return base
    return f"{base}?{urlencode(clean_params)}"


app = FastAPI(title="entries 浏览调试页", version="0.1.0")


@app.post("/api/entries/ingest")
async def api_entries_ingest(payload: Dict[str, Any]) -> Dict[str, Any]:
    """统一的 entries 写入 HTTP 接口，直接委托给 entries_ingest。

    - 适用于三栏页面、本地脚本、企业微信网关等所有通道；
    - 成功时返回 entries_ingest 的原始结果；
    - 失败时返回 HTTP 500，detail 中包含异常信息字符串（仅用于本地调试）。
    """

    try:
        result = entries_ingest(payload)
    except Exception as exc:  # noqa: BLE001
        # 作为调试用接口，直接将异常信息透传到 HTTP 响应，便于排查问题。
        raise HTTPException(status_code=500, detail=f"entries_ingest failed: {exc!r}") from exc

    if not isinstance(result, dict):
        raise HTTPException(status_code=500, detail="entries_ingest 返回结果不是 dict")

    return result


@app.get("/", response_class=HTMLResponse)
async def index(
    q: Optional[str] = Query(None, description="在 title/summary/content 上模糊搜索"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    selected_id: Optional[str] = Query(None, description="当前选中的 entry_id"),
) -> HTMLResponse:
    rows = _list_entries(q, page=page, page_size=PAGE_SIZE)

    # 选中逻辑：优先 URL 参数中的 selected_id，否则取当前页第一条
    selected: Optional[EntryRow] = None
    if selected_id:
        selected = _get_entry(selected_id)
    if selected is None and rows:
        selected = rows[0]
        selected_id = selected.entry_id

    # 计算当前选中在本页列表中的前后位置
    prev_id: Optional[str] = None
    next_id: Optional[str] = None
    if selected_id:
        for idx, r in enumerate(rows):
            if r.entry_id == selected_id:
                if idx > 0:
                    prev_id = rows[idx - 1].entry_id
                if idx < len(rows) - 1:
                    next_id = rows[idx + 1].entry_id
                break

    # 简单判断是否有“可能的上一页/下一页”
    has_prev_page = page > 1
    has_next_page = len(rows) == PAGE_SIZE

    html = _render_page(
        q=q or "",
        page=page,
        rows=rows,
        selected=selected,
        selected_id=selected_id,
        prev_id=prev_id,
        next_id=next_id,
        has_prev_page=has_prev_page,
        has_next_page=has_next_page,
    )
    return HTMLResponse(content=html)


@app.post("/delete")
async def delete_entry(  # type: ignore[override]
    entry_id: str = Form(...),
    q: str = Form(""),
    page: int = Form(1),
) -> RedirectResponse:
    """删除指定 entry 并重定向回当前查询结果页。

    仅用于本地调试页面，请谨慎使用。
    """

    _delete_entry(entry_id)
    redirect_url = _build_url("/", q=q or "", page=page)
    return RedirectResponse(url=redirect_url, status_code=303)


def _escape_html(text: str) -> str:
    import html

    return html.escape(text, quote=True)


def _render_page(
    *,
    q: str,
    page: int,
    rows: List[EntryRow],
    selected: Optional[EntryRow],
    selected_id: Optional[str],
    prev_id: Optional[str],
    next_id: Optional[str],
    has_prev_page: bool,
    has_next_page: bool,
) -> str:
    def esc(s: Optional[str]) -> str:
        return _escape_html(s or "")

    # 左侧列表 HTML
    list_items: List[str] = []
    for r in rows:
        is_active = r.entry_id == selected_id
        item_class = "entry-item active" if is_active else "entry-item"
        url = _build_url("/", q=q, page=page, selected_id=r.entry_id)
        list_items.append(
            f"""
<li class='{item_class}'>
  <a href='{url}'>
    <div class='entry-title'>{esc(r.title) or '(无标题)'}</div>
    <div class='entry-meta'>id={esc(r.entry_id)} · parent={esc(r.parent_entry_id)} · {esc(r.created_at)}</div>
  </a>
</li>
"""
        )

    list_html = "\n".join(list_items) or "<li class='entry-empty'>当前页没有记录</li>"

    # 右侧详情
    if selected is None:
        detail_html = "<div class='detail-empty'>未选中任何记录</div>"
    else:
        detail_html = f"""
<div class='detail-header'>
  <div><strong>entry_id:</strong> {esc(selected.entry_id)}</div>
  <div><strong>title:</strong> {esc(selected.title)}</div>
  <div><strong>summary_ai:</strong> {esc(selected.summary_ai)}</div>
  <div><strong>project_code:</strong> {esc(selected.project_code)}</div>
  <div><strong>user_id:</strong> {esc(selected.user_id)}</div>
  <div><strong>space_type:</strong> {esc(selected.space_type)}</div>
  <div><strong>parent_entry_id:</strong> {esc(selected.parent_entry_id)}</div>
  <div><strong>scene_tags (json):</strong> {esc(selected.scene_tags_json)}</div>
  <div><strong>created_at:</strong> {esc(selected.created_at)}</div>
</div>
<div class='detail-content-label'>原文 content：</div>
<textarea class='detail-content' readonly>{esc(selected.content)}</textarea>
"""

    # 浏览按钮（当前页内）
    nav_btns: List[str] = []
    if prev_id:
        prev_url = _build_url("/", q=q, page=page, selected_id=prev_id)
        nav_btns.append(f"<a class='btn' href='{prev_url}'>上一条 (本页)</a>")
    else:
        nav_btns.append("<span class='btn disabled'>上一条 (本页)</span>")

    if next_id:
        next_url = _build_url("/", q=q, page=page, selected_id=next_id)
        nav_btns.append(f"<a class='btn' href='{next_url}'>下一条 (本页)</a>")
    else:
        nav_btns.append("<span class='btn disabled'>下一条 (本页)</span>")

    # 分页按钮
    page_nav: List[str] = []
    if has_prev_page:
        prev_page_url = _build_url("/", q=q, page=page - 1)
        page_nav.append(f"<a class='btn' href='{prev_page_url}'>上一页</a>")
    else:
        page_nav.append("<span class='btn disabled'>上一页</span>")

    if has_next_page:
        next_page_url = _build_url("/", q=q, page=page + 1)
        page_nav.append(f"<a class='btn' href='{next_page_url}'>下一页</a>")
    else:
        page_nav.append("<span class='btn disabled'>下一页</span>")

    # 删除当前记录按钮 HTML（如果有选中记录）
    if selected_id:
        delete_form_html = (
            "<form method='post' action='/delete' style='display:inline;margin-left:8px;' "
            "onsubmit=\"return confirm('确定要删除这条记录吗？此操作不可恢复。');\">\n"
            f"  <input type='hidden' name='entry_id' value='{esc(selected_id)}' />\n"
            f"  <input type='hidden' name='q' value='{esc(q)}' />\n"
            f"  <input type='hidden' name='page' value='{page}' />\n"
            "  <button class='btn' type='submit'>删除当前记录</button>\n"
            "</form>"
        )

        # 复制当前内容按钮（仅在有选中记录时显示）
        copy_button_html = (
            "<button class='btn' type='button' onclick=\"copyCurrentContent();\">复制当前内容</button>"
        )
    else:
        delete_form_html = ""
        copy_button_html = ""

    return f"""<!DOCTYPE html>
<html lang='zh-CN'>
<head>
  <meta charset='utf-8' />
  <title>entries 调试浏览</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    .app-header {{
      padding: 8px 16px;
      border-bottom: 1px solid #ddd;
      background: #f8f8f8;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 14px;
    }}
    .app-main {{
      flex: 1;
      display: flex;
      min-height: 0;
    }}
    .sidebar {{
      width: 36%;
      border-right: 1px solid #ddd;
      display: flex;
      flex-direction: column;
      min-width: 280px;
    }}
    .sidebar-header {{
      padding: 8px;
      border-bottom: 1px solid #eee;
      background: #fafafa;
    }}
    .sidebar-list {{
      flex: 1;
      overflow: auto;
      padding: 0;
      margin: 0;
      list-style: none;
      font-size: 13px;
    }}
    .entry-item a {{
      display: block;
      padding: 6px 8px;
      text-decoration: none;
      color: #222;
    }}
    .entry-item {{
      border-bottom: 1px solid #f0f0f0;
    }}
    .entry-item:hover a {{
      background: #f0f7ff;
    }}
    .entry-item.active a {{
      background: #e3f2fd;
      border-left: 3px solid #1976d2;
      padding-left: 5px;
    }}
    .entry-title {{
      font-weight: 600;
      margin-bottom: 2px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .entry-meta {{
      color: #666;
      font-size: 11px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .entry-empty {{
      padding: 12px 8px;
      color: #888;
      font-size: 13px;
    }}
    .detail {{
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }}
    .detail-toolbar {{
      padding: 6px 10px;
      border-bottom: 1px solid #eee;
      background: #fafafa;
      display: flex;
      gap: 8px;
      align-items: center;
      font-size: 12px;
    }}
    .detail-body {{
      flex: 1;
      padding: 8px 10px;
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .detail-header > div {{
      margin-bottom: 2px;
      font-size: 13px;
    }}
    .detail-content-label {{
      margin-top: 6px;
      font-weight: 600;
      font-size: 13px;
    }}
    .detail-content {{
      width: 100%;
      flex: 1;
      resize: none;
      font-family: Consolas, 'Fira Code', monospace;
      font-size: 13px;
      border: 1px solid #ddd;
      border-radius: 4px;
      padding: 6px;
      box-sizing: border-box;
      white-space: pre-wrap;
    }}
    .detail-empty {{
      color: #777;
      font-size: 13px;
    }}
    .btn {{
      display: inline-block;
      padding: 4px 8px;
      border-radius: 3px;
      border: 1px solid #bbb;
      background: #fff;
      color: #333;
      text-decoration: none;
      font-size: 12px;
    }}
    .btn:hover {{
      background: #f0f0f0;
    }}
    .btn.disabled {{
      color: #aaa;
      border-color: #ddd;
      background: #fafafa;
      pointer-events: none;
    }}
    .search-form {{
      display: flex;
      gap: 4px;
      align-items: center;
      font-size: 12px;
    }}
    .search-input {{
      flex: 1;
      padding: 4px 6px;
      font-size: 13px;
      border-radius: 3px;
      border: 1px solid #ccc;
    }}
  </style>
</head>
<body>
  <div class='app-header'>
    <div>entries 浏览调试页 · page {page}</div>
    <div style='font-size: 12px; color: #666;'>
      说明：左侧列表 + 查询，右侧查看标题 / summary_ai / content 原文。
    </div>
  </div>
  <div class='app-main'>
    <div class='sidebar'>
      <div class='sidebar-header'>
        <form class='search-form' method='get' action='/'>
          <input class='search-input' type='text' name='q' value='{esc(q)}' placeholder='在 title/summary/content 中搜索...' />
          <input type='hidden' name='page' value='1' />
          <button class='btn' type='submit'>查询</button>
        </form>
      </div>
      <ul class='sidebar-list'>
        {list_html}
      </ul>
    </div>
    <div class='detail'>
      <div class='detail-toolbar'>
        <div>记录浏览：</div>
        {''.join(nav_btns)}
        <div style='margin-left:16px;'>分页：</div>
        {''.join(page_nav)}
        <div style='margin-left:16px; flex:1; text-align:right;'>
          {copy_button_html}
          {delete_form_html}
        </div>
      </div>
      <div class='detail-body'>
        {detail_html}
      </div>
    </div>
  </div>
  <script>
    function copyCurrentContent() {{
      var textarea = document.querySelector('.detail-content');
      if (!textarea) {{
        alert('当前没有可复制的内容');
        return;
      }}
      var text = textarea.value || textarea.textContent || '';
      if (!text) {{
        alert('当前内容为空');
        return;
      }}

      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(text).then(function () {{
          alert('已复制到剪贴板');
        }}).catch(function () {{
          fallbackCopy(textarea);
        }});
      }} else {{
        fallbackCopy(textarea);
      }}
    }}

    function fallbackCopy(element) {{
      var range = document.createRange();
      range.selectNodeContents(element);
      var selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      try {{
        document.execCommand('copy');
        alert('已复制到剪贴板');
      }} catch (err) {{
        alert('复制失败，请手动复制');
      }}
      selection.removeAllRanges();
    }}
  </script>
</body>
</html>
"""
