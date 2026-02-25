"""
财务 Agent 权限管理 v2 - 企业微信联动版

自动从企业微信获取用户部门，根据部门判断权限。
"""
import os
from typing import Optional
import requests

WECOM_CORP_ID = os.getenv("WECOM_CORP_ID", "")
WECOM_FINANCE_AGENT_SECRET = os.getenv("WECOM_FINANCE_AGENT_SECRET", "")
WECOM_APP_SECRET = os.getenv("WECOM_APP_SECRET", "")

FINANCE_DEPARTMENT_ID = 4


def _get_access_token() -> Optional[str]:
    secret = WECOM_FINANCE_AGENT_SECRET or WECOM_APP_SECRET
    if not WECOM_CORP_ID or not secret:
        return None
    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={WECOM_CORP_ID}&corpsecret={secret}"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get("errcode") == 0:
            return data.get("access_token")
    except:
        pass
    return None


def _get_user_department(userid: str) -> list:
    token = _get_access_token()
    if not token:
        return []
    url = f"https://qyapi.weixin.qq.com/cgi-bin/user/get?access_token={token}&userid={userid}"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get("errcode") == 0:
            return data.get("department", [])
    except:
        pass
    return []


def get_user_permission(userid: str) -> dict:
    departments = _get_user_department(userid)
    is_finance = FINANCE_DEPARTMENT_ID in departments
    
    if is_finance:
        return {
            "can_read_company": True,
            "can_write_company": True,
            "internal_user_id": f"user_{userid}",
            "role": "finance_staff",
            "departments": departments
        }
    else:
        return {
            "can_read_company": False,
            "can_write_company": False,
            "internal_user_id": f"user_{userid}",
            "role": "staff",
            "departments": departments
        }


def build_filter_from_permission(permission: dict, requested_scope: str) -> Optional[str]:
    if requested_scope == "company":
        if permission["can_read_company"]:
            return None
        else:
            return permission["internal_user_id"]
    return permission["internal_user_id"]


if __name__ == "__main__":
    print("=== 测试企业微信联动 ===")
    users = ["zhengyang", "wangronghua", "ZhangSan"]
    for userid in users:
        perm = get_user_permission(userid)
        print(f"{userid}: 部门={perm['departments']}, 角色={perm['role']}, 可读公司={perm['can_read_company']}")
