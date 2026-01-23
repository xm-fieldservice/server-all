#!/usr/bin/env python3
"""
企业微信消息发送测试工具
用于测试向指定用户发送消息
"""

import os
import sys
import requests
from datetime import datetime

# 加载环境变量
env_path = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

WECOM_CORP_ID = os.getenv("WECOM_CORP_ID", "")
WECOM_APP_SECRET = os.getenv("WECOM_APP_SECRET", "")
WECOM_QA_AGENT_ID = os.getenv("WECOM_QA_AGENT_ID", "")


def get_access_token():
    """获取企业微信 access_token"""
    if not WECOM_CORP_ID:
        print("❌ 错误: WECOM_CORP_ID 未配置")
        print("请先在 .env 文件中设置企业ID")
        return None
    
    if not WECOM_APP_SECRET:
        print("❌ 错误: WECOM_APP_SECRET 未配置")
        return None
    
    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={WECOM_CORP_ID}&corpsecret={WECOM_APP_SECRET}"
    
    try:
        print(f"📡 正在获取 access_token...")
        print(f"   企业ID: {WECOM_CORP_ID[:10]}...")
        resp = requests.get(url, timeout=10)
        data = resp.json()
        
        if data.get("errcode") == 0:
            token = data.get("access_token")
            print(f"✅ 获取 access_token 成功")
            return token
        else:
            print(f"❌ 获取 access_token 失败:")
            print(f"   错误码: {data.get('errcode')}")
            print(f"   错误信息: {data.get('errmsg')}")
            return None
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return None


def send_message(touser, content, agent_id=None):
    """发送文本消息"""
    if not agent_id:
        agent_id = WECOM_QA_AGENT_ID
    
    if not agent_id:
        print("❌ 错误: WECOM_QA_AGENT_ID 未配置")
        return False
    
    # 获取 access_token
    access_token = get_access_token()
    if not access_token:
        return False
    
    # 构造消息
    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
    
    payload = {
        "touser": touser,
        "msgtype": "text",
        "agentid": int(agent_id) if agent_id.isdigit() else agent_id,
        "text": {
            "content": content
        },
        "safe": 0
    }
    
    try:
        print(f"\n📤 正在发送消息...")
        print(f"   接收人: {touser}")
        print(f"   应用ID: {agent_id}")
        print(f"   内容: {content[:50]}{'...' if len(content) > 50 else ''}")
        
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        
        if data.get("errcode") == 0:
            print(f"\n✅ 消息发送成功!")
            print(f"   消息ID: {data.get('msgid', 'N/A')}")
            print(f"   无效用户: {data.get('invaliduser', '无')}")
            return True
        else:
            print(f"\n❌ 消息发送失败:")
            print(f"   错误码: {data.get('errcode')}")
            print(f"   错误信息: {data.get('errmsg')}")
            
            # 常见错误提示
            errcode = data.get('errcode')
            if errcode == 60011:
                print(f"\n💡 提示: 用户ID不存在或不在应用可见范围内")
            elif errcode == 81013:
                print(f"\n💡 提示: UserID、部门ID、标签ID全部为空或者全部不存在")
            elif errcode == 40014:
                print(f"\n💡 提示: access_token 无效")
            elif errcode == 82001:
                print(f"\n💡 提示: 应用ID不存在")
            
            return False
    except Exception as e:
        print(f"\n❌ 请求失败: {e}")
        return False


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("企业微信消息发送测试工具")
    print("=" * 60)
    
    # 检查配置
    print("\n📋 配置检查:")
    print(f"   企业ID (WECOM_CORP_ID): {'✅ 已配置' if WECOM_CORP_ID else '❌ 未配置'}")
    print(f"   应用Secret: {'✅ 已配置' if WECOM_APP_SECRET else '❌ 未配置'}")
    print(f"   应用ID (WECOM_QA_AGENT_ID): {WECOM_QA_AGENT_ID if WECOM_QA_AGENT_ID else '❌ 未配置'}")
    
    if not WECOM_CORP_ID:
        print("\n" + "=" * 60)
        print("⚠️  请先配置 WECOM_CORP_ID")
        print("=" * 60)
        print("\n步骤:")
        print("1. 登录企业微信管理后台")
        print("2. 进入「我的企业」→「企业信息」")
        print("3. 复制「企业ID」")
        print("4. 编辑 /root/.env 文件，设置:")
        print("   WECOM_CORP_ID=你的企业ID")
        print("\n" + "=" * 60)
        return
    
    # 获取用户输入
    print("\n" + "=" * 60)
    
    if len(sys.argv) > 1:
        touser = sys.argv[1]
        content = sys.argv[2] if len(sys.argv) > 2 else "🎉 测试消息\n\n这是一条来自企业微信回调通道的测试消息。\n\n发送时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        print("请输入接收消息的用户ID (企业微信成员账号):")
        print("提示: 如果不知道，可以在企业微信管理后台「通讯录」中查看")
        touser = input("用户ID: ").strip()
        
        if not touser:
            print("❌ 用户ID不能为空")
            return
        
        print("\n请输入要发送的消息内容 (直接回车使用默认测试消息):")
        content = input("消息内容: ").strip()
        
        if not content:
            content = f"🎉 测试消息\n\n这是一条来自企业微信回调通道的测试消息。\n\n发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    print("\n" + "=" * 60)
    
    # 发送消息
    success = send_message(touser, content)
    
    print("\n" + "=" * 60)
    if success:
        print("✅ 测试完成 - 消息发送成功")
        print("\n请在企业微信中查看消息")
    else:
        print("❌ 测试失败 - 请检查配置和错误提示")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
