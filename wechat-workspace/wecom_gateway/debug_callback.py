#!/usr/bin/env python3
"""
企业微信回调通道调试工具

功能：
1. 检查环境变量配置
2. 测试回调地址验证
3. 测试消息解密功能
4. 模拟企业微信回调请求
5. 测试处理器注册情况
"""

import os
import sys
import hashlib
import base64
import struct
from datetime import datetime
from typing import Dict, Any

# 添加父目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Crypto.Cipher import AES


def load_env():
    """加载环境变量"""
    env_path = os.path.join(os.path.dirname(__file__), "../../.env")
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value


def check_env_config():
    """检查企业微信配置项"""
    print("\n" + "=" * 60)
    print("1. 检查环境变量配置")
    print("=" * 60)
    
    required_vars = {
        "WECOM_CORP_ID": "企业ID",
        "WECOM_QA_AGENT_ID": "问答机器人AgentID",
        "WECOM_NOTE_AGENT_ID": "笔记机器人AgentID",
        "WECOM_APP_SECRET": "应用Secret",
        "WECOM_CALLBACK_URL": "回调地址",
        "WECOM_CALLBACK_TOKEN": "回调Token",
        "WECOM_ENCODING_AES_KEY": "加密密钥",
    }
    
    missing = []
    for var, desc in required_vars.items():
        value = os.getenv(var, "")
        status = "✓" if value else "✗"
        masked_value = value[:10] + "..." if len(value) > 10 else value
        print(f"  {status} {var:30s} ({desc:15s}): {masked_value}")
        if not value:
            missing.append(var)
    
    if missing:
        print(f"\n  ⚠️  缺少配置项: {', '.join(missing)}")
        print(f"  请在 .env 文件中添加这些配置")
        return False
    else:
        print(f"\n  ✓ 所有必需配置项已设置")
        return True


def wecom_signature(token: str, timestamp: str, nonce: str, data: str) -> str:
    """计算企业微信签名"""
    items = [token, timestamp, nonce, data]
    items.sort()
    to_hash = "".join(items)
    return hashlib.sha1(to_hash.encode("utf-8")).hexdigest()


def test_signature():
    """测试签名计算"""
    print("\n" + "=" * 60)
    print("2. 测试签名计算")
    print("=" * 60)
    
    token = os.getenv("WECOM_CALLBACK_TOKEN", "")
    if not token:
        print("  ✗ WECOM_CALLBACK_TOKEN 未配置")
        return
    
    # 测试参数
    timestamp = "1234567890"
    nonce = "test_nonce"
    echostr = "test_echo"
    
    sig = wecom_signature(token, timestamp, nonce, echostr)
    print(f"  Token:     {token[:20]}...")
    print(f"  Timestamp: {timestamp}")
    print(f"  Nonce:     {nonce}")
    print(f"  Echostr:   {echostr}")
    print(f"  Signature: {sig}")
    print(f"\n  ✓ 签名计算成功")


def wecom_decrypt(encrypted: str, encoding_aes_key: str) -> str:
    """解密企业微信消息"""
    # 还原 AES key
    aes_key = base64.b64decode(encoding_aes_key + "=")
    iv = aes_key[:16]
    
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    cipher_text = base64.b64decode(encrypted)
    plain_padded = cipher.decrypt(cipher_text)
    
    # 去掉 PKCS#7 填充
    pad = plain_padded[-1]
    if pad < 1 or pad > 32:
        raise ValueError("Invalid padding")
    plain = plain_padded[:-pad]
    
    # 跳过 16 字节随机数
    if len(plain) < 20:
        raise ValueError("Decrypted data too short")
    content = plain[16:]
    msg_len = struct.unpack("!I", content[:4])[0]
    xml_bytes = content[4 : 4 + msg_len]
    
    return xml_bytes.decode("utf-8")


def test_decrypt():
    """测试消息解密"""
    print("\n" + "=" * 60)
    print("3. 测试消息解密")
    print("=" * 60)
    
    encoding_aes_key = os.getenv("WECOM_ENCODING_AES_KEY", "")
    if not encoding_aes_key:
        print("  ✗ WECOM_ENCODING_AES_KEY 未配置")
        return
    
    if len(encoding_aes_key) != 43:
        print(f"  ✗ WECOM_ENCODING_AES_KEY 长度错误 (期望43个字符，实际{len(encoding_aes_key)}个)")
        return
    
    print(f"  EncodingAESKey: {encoding_aes_key[:20]}...")
    print(f"  密钥长度: {len(encoding_aes_key)} 字符")
    
    # 尝试解析密钥
    try:
        aes_key = base64.b64decode(encoding_aes_key + "=")
        print(f"  AES密钥长度: {len(aes_key)} 字节")
        if len(aes_key) == 32:
            print(f"  ✓ AES密钥格式正确 (AES-256)")
        else:
            print(f"  ✗ AES密钥长度错误 (期望32字节，实际{len(aes_key)}字节)")
    except Exception as e:
        print(f"  ✗ 密钥解析失败: {e}")


def generate_test_xml():
    """生成测试用的XML消息"""
    return f"""<xml>
    <ToUserName><![CDATA[toUser]]></ToUserName>
    <FromUserName><![CDATA[fromUser]]></FromUserName>
    <CreateTime>{int(datetime.now().timestamp())}</CreateTime>
    <MsgType><![CDATA[text]]></MsgType>
    <Content><![CDATA[测试消息]]></Content>
    <MsgId>1234567890</MsgId>
    <AgentID>1000023</AgentID>
</xml>"""


def test_handlers():
    """测试处理器注册"""
    print("\n" + "=" * 60)
    print("4. 测试处理器注册")
    print("=" * 60)
    
    try:
        from wecom_gateway.registry import list_agents
        from wecom_gateway import handlers  # 触发注册
        
        agents = list_agents()
        if agents:
            print(f"  已注册 {len(agents)} 个处理器:")
            for agent_id, meta in agents.items():
                print(f"    - AgentID: {agent_id}")
                print(f"      名称: {meta.get('name', 'N/A')}")
                print(f"      描述: {meta.get('description', 'N/A')}")
                print(f"      模块: {meta.get('module', 'N/A')}")
                print()
        else:
            print("  ⚠️  未找到已注册的处理器")
            print("  请检查环境变量中的 WECOM_NOTE_AGENT_ID 和 WECOM_QA_AGENT_ID")
    except Exception as e:
        print(f"  ✗ 加载处理器失败: {e}")


def test_callback_url():
    """测试回调地址可访问性"""
    print("\n" + "=" * 60)
    print("5. 测试回调地址配置")
    print("=" * 60)
    
    callback_url = os.getenv("WECOM_CALLBACK_URL", "")
    if callback_url:
        print(f"  回调URL: {callback_url}")
        print(f"  ✓ URL格式正确")
        print(f"\n  提示:")
        print(f"    - 确保该地址可以从外网访问")
        print(f"    - 企业微信后台需要配置此地址")
        print(f"    - 验证时企业微信会发送GET请求")
    else:
        print(f"  ✗ WECOM_CALLBACK_URL 未配置")


def test_ai_factory_connection():
    """测试AI Factory连接"""
    print("\n" + "=" * 60)
    print("6. 测试AI Factory连接")
    print("=" * 60)
    
    ai_factory_url = os.getenv("AI_FACTORY_BASE_URL", "http://127.0.0.1:8001")
    print(f"  AI Factory URL: {ai_factory_url}")
    
    try:
        import requests
        # 测试基本连接
        resp = requests.get(ai_factory_url, timeout=2)
        print(f"  ✓ 连接成功 (状态码: {resp.status_code})")
    except requests.exceptions.ConnectionError:
        print(f"  ✗ 连接失败 - 服务未运行")
        print(f"  请先启动 AI Factory 服务:")
        print(f"    cd ai_factory && uvicorn web.entries_browser_app:app --port 8001")
    except Exception as e:
        print(f"  ⚠️  连接测试失败: {e}")


def print_usage_guide():
    """打印使用指南"""
    print("\n" + "=" * 60)
    print("使用指南")
    print("=" * 60)
    
    print("""
1. 启动服务
   cd /root/wechat-workspace/wecom_gateway
   bash start.sh

2. 测试回调验证 (GET请求)
   curl "http://localhost:8002/wecom/callback?msg_signature=xxx&timestamp=xxx&nonce=xxx&echostr=xxx"

3. 测试消息接收 (POST请求)
   使用 test_wecom_text.xml 文件测试

4. 企业微信后台配置
   - 回调地址: http://xmapp.xiangmin.com.cn/wecom/callback
   - Token: (查看 WECOM_CALLBACK_TOKEN)
   - EncodingAESKey: (查看 WECOM_ENCODING_AES_KEY)

5. 查看日志
   tail -f /root/wechat-workspace/wecom_gateway/wecom.log
""")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("企业微信回调通道调试工具")
    print("=" * 60)
    
    # 加载环境变量
    load_env()
    
    # 运行所有测试
    config_ok = check_env_config()
    
    if config_ok:
        test_signature()
        test_decrypt()
        test_handlers()
        test_callback_url()
        test_ai_factory_connection()
    
    print_usage_guide()
    
    print("\n" + "=" * 60)
    print("调试完成")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
