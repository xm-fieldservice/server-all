import os
import json

from dotenv import load_dotenv
from openai import OpenAI

CONFIG_PATH = r"d:\\AI\\ai-factory\\deepseek-v3-chat.json"
ENV_PATH = r"d:\\AI\\ai-factory\\.env"


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    # 1. 加载 .env 环境变量
    if os.path.exists(ENV_PATH):
        load_dotenv(ENV_PATH)

    # 2. 读取 agent 的 JSON 配置
    cfg = load_config(CONFIG_PATH)
    model_client_cfg = cfg["model_client"]["config"]

    # API Key 环境变量名从 JSON 里拿
    api_key_env = model_client_cfg.get("api_key_env", "DEEPSEEK_API_KEY")
    api_key = os.getenv(api_key_env)

    if not api_key:
        raise RuntimeError(
            f"环境变量 {api_key_env} 未设置，请在 .env 或系统环境中配置 DeepSeek 的 API Key，例如：\n"
            f"{api_key_env}=你的key"
        )

    # base_url: 优先从 .env 的 DEEPSEEK_BASE_URL 读取，否则用 JSON 里的
    base_url = os.getenv("DEEPSEEK_BASE_URL", model_client_cfg["base_url"])

    model = model_client_cfg["model"]
    params = model_client_cfg.get("parameters", {})

    # 3. 配置 OpenAI 客户端为 DeepSeek 的 OpenAI 兼容接口
    client = OpenAI(api_key=api_key, base_url=base_url)

    system_message = cfg.get("system_message", "You are an AI assistant.")
    user_question = "你是谁？"

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_question},
    ]

    # 4. 发起对话（OpenAI 2.x 写法）
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=params.get("max_tokens", 1024),
        temperature=params.get("temperature", 0.7),
        top_p=params.get("top_p", 0.95),
        presence_penalty=params.get("presence_penalty", 0.0),
        frequency_penalty=params.get("frequency_penalty", 0.0),
    )

    content = response.choices[0].message.content

    print("问题：", user_question)
    print("回答：", content)


if __name__ == "__main__":
    main()
