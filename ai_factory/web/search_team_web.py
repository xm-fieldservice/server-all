from __future__ import annotations

"""Thin Web search layer for Node #2 (WEB mode).

当前实现：
- 支持多个搜索引擎：Google CSE（主）、DuckDuckGo Lite（备选）；
- 提供 web_search(query) 和 parallel_web_search_aggregate(sub_queries) 两个函数；
- 仅负责"捞网页结果"，不涉及 LLM 或多 Agent 逻辑。

代理支持：
- 通过环境变量 CLASH_HTTP_PROXY 和 CLASH_SOCKS_PROXY 配置
- 默认为 HTTP:7897, SOCKS5:7897
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

    # 如果环境变量没有设置，尝试从.env文件读取
    if not http_proxy and not socks_proxy:
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            if key.strip() == "CLASH_HTTP_PROXY" and value.strip():
                                http_proxy = value.strip()
                            elif key.strip() == "CLASH_SOCKS_PROXY" and value.strip():
                                socks_proxy = value.strip()

    if http_proxy:
        return {"http": http_proxy, "https": http_proxy}
    elif socks_proxy:
        # SOCKS5需要转换为http
        return {"http": f"socks5://{socks_proxy}", "https": f"socks5://{socks_proxy}"}
    return None


_GOOGLE_SEARCH_CFG = _get_google_search_config()
_PROXY_CFG = _get_proxy()


def _search_google_cse(query: str, num: int = 5, hl: str = "zh-cn", gl: str = "cn") -> List[Dict[str, Any]]:
    """调用 Google Custom Search API"""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": _GOOGLE_SEARCH_CFG["api_key"],
        "cx": _GOOGLE_SEARCH_CFG["cx"],
        "q": query,
        "num": max(1, min(num or 5, 10)),
        "hl": hl,
        "gl": gl,
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10, proxies=_PROXY_CFG)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", []) or []
        
        results = []
        for idx, item in enumerate(items[:num], start=1):
            results.append({
                "title": item.get("title"),
                "url": item.get("link"),
                "snippet": item.get("snippet"),
                "position": idx,
                "site": item.get("displayLink"),
                "source": "google"
            })
        return results
    except Exception as e:
        print(f"[search_google_cse] failed: {e!r}")
        return []


def _search_ddg_lite(query: str, num: int = 5) -> List[Dict[str, Any]]:
    """使用 DuckDuckGo Lite HTML 搜索（免费，无需API Key）"""
    url = "https://lite.duckduckgo.com/50x/"
    params = {
        "q": query,
        "kl": "cn-zh"
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15, proxies=_PROXY_CFG)
        resp.raise_for_status()
        
        # 解析HTML结果
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        results = []
        # DuckDuckGo Lite 的结果是每个结果在一个 div.result 里面
        for idx, result in enumerate(soup.select('div.result')[:num], start=1):
            title_elem = result.select_one('a.result__a')
            url_elem = result.select_one('a.result__url')
            snippet_elem = result.select_one('div.result__snippet')
            
            if title_elem and url_elem:
                title = title_elem.get_text(strip=True)
                url = url_elem.get_text(strip=True) if url_elem.get_text(strip=True) else url_elem.get('href', '')
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                
                # 清理URL
                if url.startswith('.'):
                    url = 'https://lite.duckduckgo.com' + url
                
                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "position": idx,
                    "source": "duckduckgo"
                })
        
        print(f"[_search_ddg_lite] got {len(results)} results for query={query!r}")
        return results
    except ImportError:
        print("[_search_ddg_lite] bs4 not installed, skipping")
        return []
    except Exception as e:
        print(f"[_search_ddg_lite] failed: {e!r}")
        return []


def _search_html_google(query: str, num: int = 5) -> List[Dict[str, Any]]:
    """直接抓取 Google 搜索结果页面（备选方案）"""
    url = "https://www.google.com/search"
    params = {"q": query, "hl": "zh-CN"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15, proxies=_PROXY_CFG)
        resp.raise_for_status()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')

        results = []
        # Google 搜索结果在 div.g 里面
        for idx, g in enumerate(soup.select('div.g')[:num], start=1):
            title_elem = g.select_one('h3')
            url_elem = g.select_one('a[href^="/url?q="]')
            snippet_elem = g.select_one('div.VwiC3b')

            if title_elem and url_elem:
                title = title_elem.get_text(strip=True)
                url = url_elem.get('href', '')
                # 清理URL
                if '/url?q=' in url:
                    from urllib.parse import parse_qs, urlparse
                    parsed = urlparse(url)
                    url = parse_qs(parsed.query).get('q', [url])[0]
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "position": idx,
                    "source": "google_html"
                })

        print(f"[_search_html_google] got {len(results)} results for query={query!r}")
        return results
    except ImportError:
        print("[_search_html_google] bs4 not installed")
        return []
    except Exception as e:
        print(f"[_search_html_google] failed: {e!r}")
        return []


def _get_serpapi_config() -> Dict[str, str]:
    api_key = os.environ.get("SERPAPI_KEY") or os.environ.get("VITE_SERPAPI_KEY")
    if not api_key:
        raise RuntimeError("未找到 SerpApi 配置，请在环境变量中设置 SERPAPI_KEY 或 VITE_SERPAPI_KEY。")
    return {"api_key": api_key}


def _search_serpapi(query: str, num: int = 5) -> List[Dict[str, Any]]:
    """使用 SerpApi 进行搜索（需要 API Key，但更稳定）"""
    try:
        config = _get_serpapi_config()
    except RuntimeError:
        print("[_search_serpapi] SerpApi config not found, skipping")
        return []

    url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": query,
        "num": min(num, 10),
        "api_key": config["api_key"]
    }

    try:
        resp = requests.get(url, params=params, timeout=15, proxies=_PROXY_CFG)
        resp.raise_for_status()
        data = resp.json()

        results = []
        organic_results = data.get("organic_results", [])

        for idx, item in enumerate(organic_results[:num], start=1):
            results.append({
                "title": item.get("title"),
                "url": item.get("link"),
                "snippet": item.get("snippet"),
                "position": idx,
                "source": "serpapi"
            })

        print(f"[_search_serpapi] got {len(results)} results for query={query!r}")
        return results
    except Exception as e:
        print(f"[_search_serpapi] failed: {e!r}")
        return []


def web_search_once(query: str, num: int = 5, *, hl: str = "zh-cn", gl: str = "cn") -> List[Dict[str, Any]]:
    """
    调用搜索引擎进行网页搜索，返回若干条精简结果。

    搜索策略（按优先级）：
    1. Google Custom Search API（主）
    2. SerpApi（稳定，需要API Key）
    3. DuckDuckGo Lite（免费备选）
    4. 直接抓取 Google HTML（无需API）

    返回元素格式：{"title", "url", "snippet", "position", "source"}
    """

    if not query.strip():
        print("[web_search_once] empty query, return []")
        return []

    # 策略1: 尝试 Google CSE
    print(f"[web_search_once] trying Google CSE for query={query!r}")
    results = _search_google_cse(query, num, hl, gl)
    if results:
        print(f"[web_search_once] Google CSE success, got {len(results)} results")
        return results

    # 策略2: 尝试 SerpApi
    print(f"[web_search_once] Google CSE failed, trying SerpApi for query={query!r}")
    results = _search_serpapi(query, num)
    if results:
        print(f"[web_search_once] SerpApi success, got {len(results)} results")
        return results

    # 策略3: 尝试 DuckDuckGo Lite
    print(f"[web_search_once] SerpApi failed, trying DuckDuckGo Lite for query={query!r}")
    results = _search_ddg_lite(query, num)
    if results:
        print(f"[web_search_once] DuckDuckGo success, got {len(results)} results")
        return results

    # 策略4: 直接抓取 Google 搜索结果页面
    print(f"[web_search_once] DuckDuckGo failed, trying Google HTML for query={query!r}")
    results = _search_html_google(query, num)
    if results:
        print(f"[web_search_once] Google HTML success, got {len(results)} results")
        return results

    # 所有策略都失败
    print(f"[web_search_once] all search engines failed for query={query!r}")
    return []


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
