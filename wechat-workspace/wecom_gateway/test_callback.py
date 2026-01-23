#!/usr/bin/env python3
"""
企业微信回调模拟测试脚本

用途：模拟企业微信发送各种类型的消息到本地服务器
"""

import os
import sys
import requests
import hashlib
from datetime import datetime

# 加载环境变量
env_path = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

BASE_URL = "http://localhost:8002"
TOKEN = os.getenv("WECOM_CALLBACK_TOKEN", "")


def wecom_signature(token: str, timestamp: str, nonce: str, data: str) -> str:
    """计算企业微信签名"""
    items = [token, timestamp, nonce, data]
    items.sort()
    to_hash = "".join(items)
    return hashlib.sha1(to_hash.encode("utf-8")).hexdigest()


def test_callback_verification():
    """测试回调地址验证 (GET请求)"""
    print("\n" + "=" * 60)
    print("测试1: 回调地址验证 (GET)")
    print("=" * 60)
    
    timestamp = str(int(datetime.now().timestamp()))
    nonce = "test_nonce_123"
    echostr = "hello_world"
    
    # 计算签名
    signature = wecom_signature(TOKEN, timestamp, nonce, echostr)
    
    # 发送请求
    url = f"{BASE_URL}/wecom/callback"
    params = {
        "msg_signature": signature,
        "timestamp": timestamp,
        "nonce": nonce,
        "echostr": echostr
    }
    
    print(f"请求URL: {url}")
    print(f"参数: {params}")
    
    try:
        resp = requests.get(url, params=params, timeout=5)
        print(f"\n状态码: {resp.status_code}")
        print(f"响应内容: {resp.text}")
        
        if resp.status_code == 200 and resp.text == echostr:
            print("✓ 验证成功！服务器返回了正确的 echostr")
        else:
            print("✗ 验证失败")
    except Exception as e:
        print(f"✗ 请求失败: {e}")


def test_text_message(agent_id="1000023", content="这是一条测试消息"):
    """测试文本消息 (POST请求)"""
    print("\n" + "=" * 60)
    print(f"测试2: 文本消息 (AgentID={agent_id})")
    print("=" * 60)
    
    timestamp = str(int(datetime.now().timestamp()))
    
    # 明文模式的 XML
    xml_content = f"""<xml>
    <ToUserName><![CDATA[ww123456]]></ToUserName>
    <FromUserName><![CDATA[TestUser]]></FromUserName>
    <CreateTime>{timestamp}</CreateTime>
    <MsgType><![CDATA[text]]></MsgType>
    <Content><![CDATA[{content}]]></Content>
    <MsgId>1234567890123456</MsgId>
    <AgentID>{agent_id}</AgentID>
</xml>"""
    
    print(f"消息内容:\n{xml_content}")
    
    url = f"{BASE_URL}/wecom/callback"
    
    try:
        resp = requests.post(
            url,
            data=xml_content.encode('utf-8'),
            headers={"Content-Type": "text/xml"},
            timeout=5
        )
        print(f"\n状态码: {resp.status_code}")
        print(f"响应内容: {resp.text}")
        
        if resp.status_code == 200 and resp.text == "success":
            print("✓ 消息发送成功")
        else:
            print("✗ 消息发送失败")
    except Exception as e:
        print(f"✗ 请求失败: {e}")


def test_note_message():
    """测试笔记消息 (AgentID=1000023)"""
    print("\n" + "=" * 60)
    print("测试3: 笔记机器人消息")
    print("=" * 60)
    
    test_text_message(
        agent_id="1000023",
        content="今天完成了企业微信回调通道的调试工作"
    )


def test_qa_message():
    """测试问答消息 (AgentID=1000025)"""
    print("\n" + "=" * 60)
    print("测试4: 问答机器人消息")
    print("=" * 60)
    
    test_text_message(
        agent_id="1000025",
        content="什么是企业微信回调？"
    )


def test_debug_endpoints():
    """测试调试接口"""
    print("\n" + "=" * 60)
    print("测试5: 调试接口")
    print("=" * 60)
    
    # 测试 debug/test_note 接口
    print("\n5.1 测试笔记调试接口")
    try:
        resp = requests.get(
            f"{BASE_URL}/debug/test_note",
            params={"userid": "test_user", "content": "测试笔记内容"},
            timeout=5
        )
        print(f"状态码: {resp.status_code}")
        print(f"响应: {resp.json()}")
        
        if resp.status_code == 200:
            print("✓ 笔记调试接口正常")
    except Exception as e:
        print(f"✗ 请求失败: {e}")


def check_service_health():
    """检查服务健康状态"""
    print("\n" + "=" * 60)
    print("检查服务状态")
    print("=" * 60)
    
    try:
        resp = requests.get(f"{BASE_URL}/docs", timeout=2)
        print(f"✓ 服务正在运行 (状态码: {resp.status_code})")
        print(f"  API文档: {BASE_URL}/docs")
        return True
    except requests.exceptions.ConnectionError:
        print(f"✗ 服务未运行")
        print(f"  请先启动服务:")
        print(f"    cd /root/wechat-workspace/wecom_gateway")
        print(f"    bash start.sh")
        return False
    except Exception as e:
        print(f"⚠️  检查失败: {e}")
        return False


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("企业微信回调模拟测试")
    print("=" * 60)
    
    if not TOKEN:
        print("\n✗ WECOM_CALLBACK_TOKEN 未配置")
        print("  请在 .env 文件中配置")
        return
    
    # 检查服务状态
    if not check_service_health():
        return
    
    # 运行测试
    print("\n开始测试...")
    
    # 1. 回调验证
    test_callback_verification()
    
    # 2. 笔记消息
    test_note_message()
    
    # 3. 问答消息
    test_qa_message()
    
    # 4. 调试接口
    test_debug_endpoints()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n提示:")
    print("  - 查看服务日志: tail -f /root/wechat-workspace/wecom_gateway/wecom.log")
    print("  - 查看API文档: http://localhost:8002/docs")
    print()


if __name__ == "__main__":
    main()
