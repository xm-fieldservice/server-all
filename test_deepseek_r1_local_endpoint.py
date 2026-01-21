from __future__ import annotations

"""最小脚本：直接测试本地 deepseek-r1:8b 的 OpenAI 兼容接口。

运行方式：
    python test_deepseek_r1_local_endpoint.py

预期：
- 如果服务正常，打印模型名和简短回复；
- 如果仍然 502 或其他错误，会把异常完整打印出来。
"""

import json

import requests


def main() -> None:
    base_url = "http://localhost:11434"
    model = "deepseek-r1:8b"

    print("[TEST] 调用本地 deepseek-r1:8b /api/generate ...")
    try:
        resp = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": "请用一句话确认：你是本地 deepseek-r1:8b 模型吗？",
                "stream": False,
            },
            timeout=600,
        )
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print("[ERROR] HTTP 调用失败:")
        print(repr(e))
        return

    try:
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        print("[ERROR] 解析 JSON 失败:")
        print(repr(e))
        print("raw:", resp.text[:500])
        return

    print("[OK] raw JSON:")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print("[OK] reply:", data.get("response"))


if __name__ == "__main__":
    main()
