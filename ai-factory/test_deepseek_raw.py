import os
import json
from urllib import request, error
from pathlib import Path

# 优先尝试加载当前目录下的 .env，以便从文件中读取 DEEPSEEK_API_KEY
try:
    from dotenv import load_dotenv  # type: ignore

    current_dir = Path(__file__).resolve().parent
    load_dotenv(dotenv_path=current_dir / ".env", override=False)
except Exception:
    # 未安装 python-dotenv 或 .env 缺失时，忽略错误，继续走系统环境变量
    pass

API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
BASE_URL = "https://api.deepseek.com/v1"

if not API_KEY:
    print("DEEPSEEK_API_KEY 未设置")
    raise SystemExit(1)

url = f"{BASE_URL}/chat/completions"
body = {
    "model": "deepseek-chat",
    "messages": [
        {"role": "user", "content": "请用中文说：这是一次直连 DeepSeek 的测试，不要说你不会回答。"}
    ]
}
data = json.dumps(body).encode("utf-8")
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

req = request.Request(url, data=data, headers=headers, method="POST")

try:
    with request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
        print("HTTP 状态:", resp.status)
        print("响应原文:\n", raw)
except error.HTTPError as e:
    try:
        raw = e.read().decode("utf-8")
        print("HTTPError 状态:", e.code)
        print("错误响应:\n", raw)
    except Exception:
        print("HTTPError:", e)
except Exception as e:
    print("请求失败:", repr(e))
