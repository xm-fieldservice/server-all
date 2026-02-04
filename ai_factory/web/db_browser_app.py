from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

from ai_factory.db.pgvector_client import connection_scope


app = FastAPI(title="ai-factory-db-browser", version="0.3.0")


PAGE_SIZE = 50


@dataclass
class EntryRow:
    entry_id: str
    title: Optional[str]
    summary_ai: Optional[str]
    content: Optional[str]
    project_code: Optional[str]
    user_id: Optional[str]
    created_at: Optional[str]
    answer_payload: Optional[Dict[str, Any]]


def _list_entries(q: str, page: int, page_size: int = PAGE_SIZE) -> Tuple[List[EntryRow], int]:
    """按搜索条件与分页列出 entries。

    返回 (rows, total_count)。
    """

    offset = max(page - 1, 0) * page_size

    base_sql = """
        FROM entries
        WHERE 1=1
    """

    params: List[Any] = []

    if q:
        like = f"%{q}%"
        base_sql += " AND (title ILIKE %s OR summary_ai ILIKE %s OR input_content ILIKE %s)"
        params.extend([like, like, like])

    count_sql = "SELECT COUNT(*) " + base_sql
    list_sql = (
        "SELECT entry_id, title, summary_ai, input_content AS content, project_code, user_id, "
        "to_char(created_at AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS') AS created_at, "
        "answer_payload AS answer_payload "
        + base_sql
        + " ORDER BY created_at DESC, entry_id DESC LIMIT %s OFFSET %s"
    )

    with connection_scope() as conn:
        with conn.cursor() as cur:
            # count
            cur.execute(count_sql, params)
            total_count = int(cur.fetchone()[0])

            # list
            cur.execute(list_sql, params + [page_size, offset])
            rows = cur.fetchall()

    items: List[EntryRow] = []
    for r in rows:
        items.append(
            EntryRow(
                entry_id=str(r[0]),
                title=r[1],
                summary_ai=r[2],
                content=r[3],
                project_code=r[4],
                user_id=r[5],
                created_at=str(r[6]) if r[6] is not None else None,
                answer_payload=r[7] if len(r) > 7 else None,
            )
        )

    return items, total_count


def _get_entry_detail(entry_id: str) -> Optional[Dict[str, Any]]:
    sql = (
        "SELECT e.*, to_char(e.created_at AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS') AS created_at_sh "
        "FROM entries e WHERE e.entry_id = %s"
    )
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (entry_id,))
            row = cur.fetchone()
            if row is None:
                return None
            colnames = [d[0] for d in cur.description]
    return dict(zip(colnames, row))


def _render_detail_fragment(selected_detail: Dict[str, Any]) -> str:
    key_fields = [
        "entry_id",
        "title",
        "summary_ai",
        "project_code",
        "user_id",
        "workspace_id",
        "note_datetime",
        "created_at",
    ]
    detail_header_parts: List[str] = []
    for k in key_fields:
        if k in selected_detail:
            v = selected_detail.get("created_at_sh") if k == "created_at" and "created_at_sh" in selected_detail else selected_detail.get(k)
            detail_header_parts.append(
                f"<div><strong>{k}:</strong> {'' if v is None else v}</div>"
            )

    content_value = selected_detail.get("input_content" if "input_content" in selected_detail else "content")

    memo_value = None
    if "answer_payload" in selected_detail:
        memo_value = selected_detail.get("answer_payload")
    elif "memo" in selected_detail:
        memo_value = selected_detail.get("memo")
    answer_payload_html = ""
    if memo_value is not None:
        import json
        try:
            if isinstance(memo_value, str):
                memo_value = json.loads(memo_value)
            memo_formatted = json.dumps(memo_value, ensure_ascii=False, indent=2)
        except Exception:
            memo_formatted = str(memo_value)
    else:
        memo_formatted = "null"
    answer_payload_html = f"""
    <div class="detail-content-label">Answer Payload (JSON)：</div>
    <pre id="detail-answer-payload" class="detail-content">{memo_formatted}</pre>
    """

    extra_fields_parts: List[str] = []
    for k, v in selected_detail.items():
        if k in key_fields or k in ("content", "input_content", "memo", "answer_payload"):
            continue
        extra_fields_parts.append(
            """
            <div class="field-block">
              <div class="field-label">{k}</div>
              <pre class="field-pre">{v}</pre>
            </div>
            """.format(k=k, v="" if v is None else v)
        )

    return """
    <div class="detail-header">
      {header}
    </div>
    <div class="detail-content-label">原文 input_content：</div>
    <pre id="detail-content" class="detail-content">{content}</pre>
    {memo}
    <div class="detail-extra">
      {extra}
    </div>
    """.format(
        header="\n".join(detail_header_parts),
        content="" if content_value is None else content_value,
        memo=answer_payload_html,
        extra="\n".join(extra_fields_parts),
    )


@app.get("/detail_html", response_class=HTMLResponse)
async def detail_html(entry_id: str) -> str:
    d = _get_entry_detail(entry_id)
    if not d:
        return "<div class=\"detail-empty\">未选中任何记录</div>"
    return _render_detail_fragment(d)

def _render_page(
    *,
    q: str,
    page: int,
    page_size: int,
    rows: List[EntryRow],
    total_count: int,
    selected_detail: Optional[Dict[str, Any]],
) -> str:
    total_pages = max((total_count + page_size - 1) // page_size, 1)
    page = max(1, min(page, total_pages))

    # 左侧列表 HTML
    list_items_html: List[str] = []
    selected_id = str(selected_detail.get("entry_id")) if selected_detail else None

    for r in rows:
        is_active = selected_id is not None and str(r.entry_id) == selected_id
        active_class = " active" if is_active else ""
        title = r.title or "(无标题)"
        meta = f"id={r.entry_id} b7 {r.created_at or ''}"
        list_items_html.append(
            """
            <li class="entry-item{active}">
              <a href="#" onclick="return selectEntry('{entry_id}', this)">
                <div class="entry-title">{title}</div>
                <div class="entry-meta">{meta}</div>
              </a>
            </li>
            """.format(active=active_class, entry_id=r.entry_id, title=title, meta=meta)
        )

    list_html = "\n".join(list_items_html) if list_items_html else "<li class=\"entry-empty\">暂无记录</li>"

    # 右侧详情区：先挑几个关键字段，其次把所有字段遍历一遍
    if selected_detail:
        key_fields = [
            "entry_id",
            "title",
            "summary_ai",
            "project_code",
            "user_id",
            "workspace_id",
            "note_datetime",
            "created_at",
        ]
        detail_header_parts: List[str] = []
        for k in key_fields:
            if k in selected_detail:
                v = selected_detail.get("created_at_sh") if k == "created_at" and "created_at_sh" in selected_detail else selected_detail.get(k)
                detail_header_parts.append(
                    f"<div><strong>{k}:</strong> {'' if v is None else v}</div>"
                )

        # content 作为大块正文
        content_value = selected_detail.get("input_content" if "input_content" in selected_detail else "content")

        # memo/answer_payload 作为单独的大块（JSON 格式化）
        memo_value = None
        if "answer_payload" in selected_detail:
            memo_value = selected_detail.get("answer_payload")
        elif "memo" in selected_detail:
            memo_value = selected_detail.get("memo")
        answer_payload_html = ""
        if memo_value is not None:
            # 将 memo 值格式化为可读的 JSON
            import json
            try:
                if isinstance(memo_value, str):
                    memo_value = json.loads(memo_value)
                memo_formatted = json.dumps(memo_value, ensure_ascii=False, indent=2)
            except Exception:
                memo_formatted = str(memo_value)
        else:
            memo_formatted = "null"
        answer_payload_html = f"""
        <div class="detail-content-label">Answer Payload (JSON)：</div>
        <pre id="detail-answer-payload" class="detail-content">{memo_formatted}</pre>
        """

        # 其余字段
        extra_fields_parts: List[str] = []
        for k, v in selected_detail.items():
            if k in key_fields or k in ("content", "input_content", "memo", "answer_payload"):
                continue
            extra_fields_parts.append(
                """
                <div class="field-block">
                  <div class="field-label">{k}</div>
                  <pre class="field-pre">{v}</pre>
                </div>
                """.format(k=k, v="" if v is None else v)
            )

        detail_html = """
        <div class="detail-header">
          {header}
        </div>
        <div class="detail-content-label">原文 input_content：</div>
        <pre id="detail-content" class="detail-content">{content}</pre>
        {memo}
        <div class="detail-extra">
          {extra}
        </div>
        """.format(
            header="\n".join(detail_header_parts),
            content="" if content_value is None else content_value,
            memo=answer_payload_html,
            extra="\n".join(extra_fields_parts),
        )
    else:
        detail_html = "<div class=\"detail-empty\">未选中任何记录</div>"

    q_display = q or ""

    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <title>AI Factory DB Browser</title>
        <style>
          body {{
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background-color: #fafafa;
          }}
          .app-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 12px;
            border-bottom: 1px solid #ddd;
            background: #f7f7f7;
          }}
          .app-main {{
            display: flex;
            height: calc(100vh - 44px);
          }}
          .sidebar {{
            width: 34%;
            border-right: 1px solid #ddd;
            display: flex;
            flex-direction: column;
          }}
          .sidebar-header {{
            padding: 8px 12px;
            border-bottom: 1px solid #eee;
          }}
          .sidebar-list {{
            list-style: none;
            margin: 0;
            padding: 0;
            overflow-y: auto;
            flex: 1;
            background: #fff;
          }}
          .entry-item a {{
            display: block;
            padding: 8px 12px;
            text-decoration: none;
            color: inherit;
          }}
          .entry-item {{
            border-bottom: 1px solid #f0f0f0;
          }}
          .entry-item:hover {{
            background-color: #f5f5f5;
          }}
          .entry-item.active {{
            background-color: #e6f7ff;
            border-left: 3px solid #1677ff;
          }}
          .entry-title {{
            font-size: 14px;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }}
          .entry-meta {{
            font-size: 12px;
            color: #666;
            margin-top: 2px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }}
          .entry-empty {{
            padding: 12px;
            color: #999;
          }}
          .detail {{
            flex: 1;
            display: flex;
            flex-direction: column;
            padding: 12px 16px;
            overflow: hidden;
          }}
          .detail-toolbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            font-size: 13px;
          }}
          .detail-body {{
            flex: 1;
            overflow-y: auto;
            background: #fff;
            border: 1px solid #eee;
            border-radius: 4px;
            padding: 12px;
          }}
          .detail-header {{
            margin-bottom: 8px;
            font-size: 13px;
          }}
          .detail-content-label {{
            margin: 8px 0 4px;
            font-weight: 600;
          }}
          .detail-content {{
            background: #fafafa;
            padding: 8px;
            border-radius: 4px;
            border: 1px solid #eee;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 320px;
            overflow-y: auto;
            font-size: 13px;
          }}
          .detail-extra {{
            margin-top: 12px;
          }}
          .field-block {{
            margin-bottom: 8px;
          }}
          .field-label {{
            font-weight: 600;
            font-size: 12px;
          }}
          .field-pre {{
            background: #fafafa;
            padding: 6px;
            border-radius: 4px;
            border: 1px solid #eee;
            white-space: pre-wrap;
            word-break: break-word;
            font-size: 12px;
          }}
          .btn {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            border: 1px solid #d9d9d9;
            background: #fff;
            font-size: 12px;
            cursor: pointer;
          }}
          .btn.primary {{
            background: #1677ff;
            border-color: #1677ff;
            color: #fff;
          }}
          .search-form {{
            display: flex;
            gap: 4px;
          }}
          .search-input {{
            flex: 1;
            padding: 4px 6px;
            font-size: 13px;
          }}
        </style>
      </head>
      <body>
        <div class="app-header">
          <div>entries 浏览调试页 · page {page}/{total_pages} · total {total_count}</div>
          <div style="font-size:12px;color:#666;">
            左侧列表 + 查询，右侧查看标题 / summary_ai / content / 提交人等字段。
          </div>
        </div>
        <div class="app-main">
          <div class="sidebar">
            <div class="sidebar-header">
              <form class="search-form" method="get" action="/">
                <input class="search-input" type="text" name="q" value="{q_display}" placeholder="在标题 / 摘要 / 正文中搜索" />
                <input type="hidden" name="page" value="1" />
                <button class="btn" type="submit">查询</button>
              </form>
            </div>
            <ul class="sidebar-list">
              {list_html}
            </ul>
          </div>
          <div class="detail">
            <div class="detail-toolbar">
              <div>
                记录浏览：page {page}/{total_pages}
              </div>
              <div>
                <button class="btn" type="button" onclick="copyContent()">复制当前 content</button>
                <button class="btn" style="margin-left:8px;color:#fff;background:#ff4d4f;border-color:#ff4d4f;" type="button" onclick="deleteEntry()">删除</button>
              </div>
            </div>
            <div class="detail-body">
              {detail_html}
            </div>
          </div>
        </div>

        <script>
          var selectedId = "{selected_id}";
          function copyContent() {{
            var el = document.getElementById('detail-content');
            if (!el) {{
              alert('没有可复制的内容');
              return;
            }}
            var text = el.innerText || el.textContent || '';
            if (!text) {{
              alert('当前 content 为空');
              return;
            }}
            if (navigator.clipboard && navigator.clipboard.writeText) {{
              navigator.clipboard.writeText(text).then(function() {{
                alert('已复制当前 content 到剪贴板');
              }}).catch(function(err) {{
                console.error('clipboard.writeText failed', err);
                fallbackCopy(text);
              }});
            }} else {{
              fallbackCopy(text);
            }}
          }}

          function fallbackCopy(text) {{
            var textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {{
              var ok = document.execCommand('copy');
              if (ok) {{
                alert('已复制当前 content 到剪贴板');
              }} else {{
                alert('复制失败，请手动选择内容复制');
              }}
            }} catch (e) {{
              console.error('execCommand(copy) failed', e);
              alert('复制失败，请手动选择内容复制');
            }}
            document.body.removeChild(textarea);
          }}
          function selectEntry(id, anchorEl) {{
            fetch('/detail_html?entry_id=' + encodeURIComponent(id))
              .then(function(resp) {{ return resp.text(); }})
              .then(function(html) {{
                var body = document.querySelector('.detail-body');
                if (body) {{ body.innerHTML = html; }}
                selectedId = id;
                // active 切换
                try {{
                  document.querySelectorAll('.entry-item').forEach(function(li) {{ li.classList.remove('active'); }});
                  if (anchorEl) {{
                    var li = anchorEl.closest('.entry-item');
                    if (li) {{ li.classList.add('active'); }}
                  }}
                }} catch (e) {{}}
                // 更新 URL 的 selected_id 但不刷新
                try {{
                  var url = new URL(window.location.href);
                  url.searchParams.set('selected_id', id);
                  window.history.replaceState({{}}, '', url.toString());
                }} catch (e) {{}}
              }})
              .catch(function(err) {{
                alert('加载详情失败: ' + err);
              }});
            return false;
          }}
        </script>
        <script>
          function deleteEntry() {{
            var q = "{q}";
            var page = {page};
            if (!selectedId) {{
              alert('未选中任何记录，无法删除');
              return;
            }}
            if (!confirm('确认删除该记录？(同时删除其 embedding)')) {{
              return;
            }}
            var url = '/delete?entry_id=' + encodeURIComponent(selectedId) + '&q=' + encodeURIComponent(q) + '&page=' + page;
            window.location.href = url;
          }}
        </script>
      </body>
    </html>
    """
    return html


@app.get("/", response_class=HTMLResponse)
async def index(q: str = "", page: int = 1, selected_id: Optional[str] = None) -> str:
    page = max(page, 1)
    rows, total_count = _list_entries(q=q.strip(), page=page, page_size=PAGE_SIZE)

    selected_detail: Optional[Dict[str, Any]] = None
    if selected_id:
        selected_detail = _get_entry_detail(selected_id)
    if not selected_detail and rows:
        selected_detail = _get_entry_detail(rows[0].entry_id)

    return _render_page(
        q=q.strip(),
        page=page,
        page_size=PAGE_SIZE,
        rows=rows,
        total_count=total_count,
        selected_detail=selected_detail,
    )


@app.get("/delete")
async def delete(entry_id: str, q: str = "", page: int = 1) -> RedirectResponse:
    if entry_id:
        with connection_scope() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("DELETE FROM entry_embeddings WHERE entry_id = %s", (entry_id,))
                except Exception:
                    pass
                cur.execute("DELETE FROM entries WHERE entry_id = %s", (entry_id,))
    return RedirectResponse(url=f"/?q={q}&page={page}", status_code=303)
