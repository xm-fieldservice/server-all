from __future__ import annotations

"""Thin Web search layer for Node #2 (WEB mode).

当前实现：
- 直接使用 Google Custom Search（与旧 search_team_backend 保持一致）；
- 提供 web_search(query) 和 parallel_web_search_aggregate(sub_queries) 两个函数；
- 仅负责"捞网页结果"，不涉及 LLM 或多 Agent 逻辑。

代理支持：
- 通过环境变量 CLASH_HTTP_PROXY 和 CLASH_SOCKS_PROXY 配置
- 默认为 HTTP:7890, SOCKS5:7891
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

import requests


def _get_google_search_config() -> Dict[str, str]:
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY")
    cx = os.environ.get("GOOGLE_SEARCH_ENGINE_ID")
    if not api_key or not cx:
        raise RuntimeError(
            "未找到 Google Custom Search 配置，请在环境变量中设置 "
            "GOOGLE_SEARCH_API_KEY 和 GOOGLE_SEARCH_ENGINE_ID。"
        )
    return {"api_key": api_key, "cx": cx}


def _get_proxy() -> Dict[str, str] | None:
    """获取代理配置"""
    http_proxy = os.environ.get("CLASH_HTTP_PROXY") or os.environ.get("HTTP_PROXY")
    socks_proxy = os.environ.get("CLASH_SOCKS_PROXY") or os.environ.get("SOCKS_PROXY")
    
    if http_proxy:
        return {"http": http_proxy, "https": http_proxy}
    elif socks_proxy:
        # SOCKS5需要转换为http
        return {"http": f"socks5://{socks_proxy}", "https": f"socks5://{socks_proxy}"}
    return None


_GOOGLE_SEARCH_CFG = _get_google_search_config()
_PROXY_CFG = _get_proxy()


def web_search_once(query: str, num: int = 5, *, hl: str = "zh-cn", gl: str = "cn") -> List[Dict[str, Any]]:
    """调用 Google Custom Search 进行一次网页搜索，返回若干条精简结果。

    返回元素格式：{"title", "url", "snippet", "position"}，额外保留原始 site 信息（若有）。
    """

    if not query.strip():
        print("[web_search_once] empty query, return []")
        return []

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": _GOOGLE_SEARCH_CFG["api_key"],
        "cx": _GOOGLE_SEARCH_CFG["cx"],
        "q": query,
        "num": max(1, min(num or 5, 10)),
        "hl": hl,
        "gl": gl,
    }

    print("[web_search_once] sending request to Google CSE, params:", params)

    # 使用较短超时时间，并捕获所有请求异常，避免在网络受限环境下长时间卡死。
    try:
        resp = requests.get(url, params=params, timeout=10, proxies=_PROXY_CFG)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        print(f"[web_search_once] request failed for query={query!r}: {e!r}")
        if _PROXY_CFG:
            print(f"[web_search_once] 代理配置: {_PROXY_CFG}")
        return []
    items = data.get("items", []) or []

    simplified: List[Dict[str, Any]] = []
    for idx, item in enumerate(items[: num or 5], start=1):
        simplified.append(
            {
                "title": item.get("title"),
                "url": item.get("link"),
                "snippet": item.get("snippet"),
                "position": idx,
                # 可选字段，供前端或后续处理使用
                "site": item.get("displayLink"),
            }
        )

    print(f"[web_search_once] got {len(simplified)} items for query={query!r}")

    return simplified


def parallel_web_search_aggregate(
    sub_queries: List[Dict[str, Any]],
    *,
    num: int = 5,
    max_workers: int = 3,
) -> List[Dict[str, Any]]:
    """并发执行多条子查询的 web_search 聚合。

    - sub_queries: 期望每项至少包含 {"query": str} 或 {"q": str}；
    - 为每条结果附加 subquery_index 字段，指明来源子查询下标。
    """

    print("[parallel_web_search_aggregate] called with sub_queries:", sub_queries)

    aggregated_results: List[Dict[str, Any]] = []
    if not sub_queries:
        print("[parallel_web_search_aggregate] no sub_queries, return []")
        return aggregated_results

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {}
        for idx, item in enumerate(sub_queries):
            q = str(item.get("query") or item.get("q") or "").strip()
            if not q:
                print(f"[parallel_web_search_aggregate] skip empty query at index {idx}")
                continue
            print(f"[parallel_web_search_aggregate] submit query index {idx}: {q!r}")
            future = executor.submit(web_search_once, q, num)
            future_to_idx[future] = idx

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results = future.result()
            except Exception as e:
                print(f"[parallel_web_search_aggregate] query index {idx} failed: {e!r}")
                continue
            print(f"[parallel_web_search_aggregate] query index {idx} returned {len(results)} results")
            for r in results:
                record = dict(r)
                record["subquery_index"] = idx
                aggregated_results.append(record)

    print("[parallel_web_search_aggregate] aggregated_results count =", len(aggregated_results))

    return aggregated_results
