"""
企业微信组织架构和权限管理底座

功能：
1. 同步企业微信部门架构
2. 同步用户信息和部门归属
3. 权限管理和角色映射
4. 缓存和定期更新机制
"""

import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
import requests


# 配置
WECOM_CORP_ID = os.getenv("WECOM_CORP_ID", "")
WECOM_APP_SECRET = os.getenv("WECOM_APP_SECRET", "")
WECOM_NOTE_AGENT_ID = os.getenv("WECOM_NOTE_AGENT_ID", "")

# 缓存数据
_ACCESS_TOKEN_CACHE: Dict[str, Any] = {}
_DEPARTMENTS: Dict[int, Dict[str, Any]] = {}  # dept_id -> dept_info
_USERS: Dict[str, Dict[str, Any]] = {}  # userid -> user_info
_USER_DEPT_MAP: Dict[str, Set[int]] = {}  # userid -> set of dept_ids
_DEPT_USERS_MAP: Dict[int, Set[str]] = {}  # dept_id -> set of userids

# 上次同步时间
_LAST_SYNC_TIME: Optional[datetime] = None
SYNC_INTERVAL = timedelta(hours=1)  # 同步间隔


class WeComAPIError(Exception):
    """企业微信API错误"""
    pass


def get_access_token(force_refresh: bool = False) -> str:
    """获取企业微信access_token
    
    Args:
        force_refresh: 强制刷新token
        
    Returns:
        access_token
    """
    global _ACCESS_TOKEN_CACHE
    
    if not WECOM_CORP_ID or not WECOM_APP_SECRET:
        raise WeComAPIError("WECOM_CORP_ID 或 WECOM_APP_SECRET 未配置")
    
    # 检查缓存
    if not force_refresh and _ACCESS_TOKEN_CACHE:
        expires_at = _ACCESS_TOKEN_CACHE.get("expires_at", 0)
        if time.time() < expires_at:
            return _ACCESS_TOKEN_CACHE["access_token"]
    
    # 请求新token
    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={WECOM_CORP_ID}&corpsecret={WECOM_APP_SECRET}"
    
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        
        if data.get("errcode") != 0:
            raise WeComAPIError(f"获取access_token失败: {data.get('errmsg')}")
        
        access_token = data["access_token"]
        expires_in = data.get("expires_in", 7200)
        
        # 缓存token（提前5分钟过期）
        _ACCESS_TOKEN_CACHE = {
            "access_token": access_token,
            "expires_at": time.time() + expires_in - 300
        }
        
        return access_token
    
    except requests.RequestException as e:
        raise WeComAPIError(f"请求access_token失败: {e}") from e


def sync_departments(parent_id: int = 0) -> List[Dict[str, Any]]:
    """同步部门列表
    
    Args:
        parent_id: 父部门ID，0表示根部门
        
    Returns:
        部门列表
    """
    access_token = get_access_token()
    url = f"https://qyapi.weixin.qq.com/cgi-bin/department/list?access_token={access_token}"
    
    if parent_id:
        url += f"&id={parent_id}"
    
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        
        if data.get("errcode") != 0:
            raise WeComAPIError(f"获取部门列表失败: {data.get('errmsg')}")
        
        departments = data.get("department", [])
        
        # 更新缓存
        for dept in departments:
            dept_id = dept["id"]
            _DEPARTMENTS[dept_id] = {
                "id": dept_id,
                "name": dept["name"],
                "name_en": dept.get("name_en", ""),
                "parent_id": dept.get("parentid", 0),
                "order": dept.get("order", 0),
                "synced_at": datetime.now().isoformat()
            }
        
        return departments
    
    except requests.RequestException as e:
        raise WeComAPIError(f"请求部门列表失败: {e}") from e


def sync_department_users(dept_id: int, fetch_child: bool = False) -> List[Dict[str, Any]]:
    """同步部门成员
    
    Args:
        dept_id: 部门ID
        fetch_child: 是否递归获取子部门成员
        
    Returns:
        用户列表
    """
    access_token = get_access_token()
    url = (
        f"https://qyapi.weixin.qq.com/cgi-bin/user/list"
        f"?access_token={access_token}&department_id={dept_id}"
    )
    
    if fetch_child:
        url += "&fetch_child=1"
    
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        
        if data.get("errcode") != 0:
            raise WeComAPIError(f"获取部门成员失败: {data.get('errmsg')}")
        
        users = data.get("userlist", [])
        
        # 更新缓存
        for user in users:
            userid = user["userid"]
            _USERS[userid] = {
                "userid": userid,
                "name": user["name"],
                "alias": user.get("alias", ""),
                "mobile": user.get("mobile", ""),
                "department": user.get("department", []),
                "position": user.get("position", ""),
                "gender": user.get("gender", "0"),
                "email": user.get("email", ""),
                "is_leader_in_dept": user.get("is_leader_in_dept", []),
                "avatar": user.get("avatar", ""),
                "status": user.get("status", 0),  # 1=已激活 2=已禁用 4=未激活
                "qr_code": user.get("qr_code", ""),
                "synced_at": datetime.now().isoformat()
            }
            
            # 更新用户-部门映射
            dept_ids = user.get("department", [])
            _USER_DEPT_MAP[userid] = set(dept_ids)
            
            # 更新部门-用户映射
            for dept_id in dept_ids:
                if dept_id not in _DEPT_USERS_MAP:
                    _DEPT_USERS_MAP[dept_id] = set()
                _DEPT_USERS_MAP[dept_id].add(userid)
        
        return users
    
    except requests.RequestException as e:
        raise WeComAPIError(f"请求部门成员失败: {e}") from e


def get_user_detail(userid: str) -> Dict[str, Any]:
    """获取用户详细信息
    
    Args:
        userid: 用户ID
        
    Returns:
        用户信息
    """
    # 先检查缓存
    if userid in _USERS:
        cached_user = _USERS[userid]
        # 如果缓存时间不超过1小时，直接返回
        synced_at = cached_user.get("synced_at")
        if synced_at:
            try:
                synced_time = datetime.fromisoformat(synced_at)
                if datetime.now() - synced_time < timedelta(hours=1):
                    return cached_user
            except ValueError:
                pass
    
    # 从API获取
    access_token = get_access_token()
    url = f"https://qyapi.weixin.qq.com/cgi-bin/user/get?access_token={access_token}&userid={userid}"
    
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        
        if data.get("errcode") != 0:
            raise WeComAPIError(f"获取用户信息失败: {data.get('errmsg')}")
        
        user_info = {
            "userid": data["userid"],
            "name": data["name"],
            "alias": data.get("alias", ""),
            "mobile": data.get("mobile", ""),
            "department": data.get("department", []),
            "position": data.get("position", ""),
            "gender": data.get("gender", "0"),
            "email": data.get("email", ""),
            "is_leader_in_dept": data.get("is_leader_in_dept", []),
            "avatar": data.get("avatar", ""),
            "status": data.get("status", 0),
            "qr_code": data.get("qr_code", ""),
            "synced_at": datetime.now().isoformat()
        }
        
        # 更新缓存
        _USERS[userid] = user_info
        
        # 更新映射关系
        dept_ids = user_info["department"]
        _USER_DEPT_MAP[userid] = set(dept_ids)
        
        return user_info
    
    except requests.RequestException as e:
        raise WeComAPIError(f"请求用户信息失败: {e}") from e


def sync_all_org_data() -> Dict[str, Any]:
    """同步所有组织架构数据
    
    Returns:
        同步结果统计
    """
    global _LAST_SYNC_TIME
    
    start_time = time.time()
    stats = {
        "departments": 0,
        "users": 0,
        "errors": []
    }
    
    try:
        # 1. 同步所有部门
        print("[同步] 开始同步部门架构...")
        departments = sync_departments()
        stats["departments"] = len(departments)
        print(f"[同步] 同步了 {len(departments)} 个部门")
        
        # 2. 同步每个部门的成员
        print("[同步] 开始同步部门成员...")
        total_users = 0
        for dept in departments:
            dept_id = dept["id"]
            try:
                users = sync_department_users(dept_id)
                total_users += len(users)
                print(f"[同步] 部门 {dept['name']} ({dept_id}): {len(users)} 个成员")
            except WeComAPIError as e:
                error_msg = f"同步部门 {dept_id} 失败: {e}"
                print(f"[错误] {error_msg}")
                stats["errors"].append(error_msg)
        
        stats["users"] = len(_USERS)  # 去重后的总用户数
        
        _LAST_SYNC_TIME = datetime.now()
        
        elapsed = time.time() - start_time
        print(f"[同步] 完成！耗时 {elapsed:.2f}秒")
        print(f"[同步] 部门: {stats['departments']}, 用户: {stats['users']}")
        
    except WeComAPIError as e:
        error_msg = f"同步失败: {e}"
        print(f"[错误] {error_msg}")
        stats["errors"].append(error_msg)
    
    return stats


def get_department(dept_id: int) -> Optional[Dict[str, Any]]:
    """获取部门信息"""
    return _DEPARTMENTS.get(dept_id)


def get_user(userid: str) -> Optional[Dict[str, Any]]:
    """获取用户信息"""
    return _USERS.get(userid)


def get_user_departments(userid: str) -> List[Dict[str, Any]]:
    """获取用户所属部门列表"""
    dept_ids = _USER_DEPT_MAP.get(userid, set())
    return [_DEPARTMENTS[dept_id] for dept_id in dept_ids if dept_id in _DEPARTMENTS]


def get_department_users(dept_id: int, include_children: bool = False) -> List[Dict[str, Any]]:
    """获取部门成员列表
    
    Args:
        dept_id: 部门ID
        include_children: 是否包含子部门成员
        
    Returns:
        用户列表
    """
    user_ids = set()
    
    # 当前部门的成员
    if dept_id in _DEPT_USERS_MAP:
        user_ids.update(_DEPT_USERS_MAP[dept_id])
    
    # 子部门成员
    if include_children:
        child_depts = get_child_departments(dept_id)
        for child_dept in child_depts:
            child_dept_id = child_dept["id"]
            if child_dept_id in _DEPT_USERS_MAP:
                user_ids.update(_DEPT_USERS_MAP[child_dept_id])
    
    return [_USERS[uid] for uid in user_ids if uid in _USERS]


def get_child_departments(parent_id: int) -> List[Dict[str, Any]]:
    """获取子部门列表（不递归）"""
    return [
        dept for dept in _DEPARTMENTS.values()
        if dept["parent_id"] == parent_id
    ]


def get_all_child_departments(parent_id: int) -> List[Dict[str, Any]]:
    """获取所有子部门列表（递归）"""
    result = []
    direct_children = get_child_departments(parent_id)
    
    for child in direct_children:
        result.append(child)
        # 递归获取子部门的子部门
        result.extend(get_all_child_departments(child["id"]))
    
    return result


def is_user_in_department(userid: str, dept_id: int, include_children: bool = False) -> bool:
    """检查用户是否在指定部门
    
    Args:
        userid: 用户ID
        dept_id: 部门ID
        include_children: 是否包含子部门
        
    Returns:
        是否在部门中
    """
    user_depts = _USER_DEPT_MAP.get(userid, set())
    
    if dept_id in user_depts:
        return True
    
    if include_children:
        # 检查是否在子部门
        child_depts = get_all_child_departments(dept_id)
        child_dept_ids = {d["id"] for d in child_depts}
        return bool(user_depts & child_dept_ids)
    
    return False


def is_department_leader(userid: str, dept_id: int) -> bool:
    """检查用户是否是部门负责人"""
    user = _USERS.get(userid)
    if not user:
        return False
    
    user_depts = user.get("department", [])
    is_leader_list = user.get("is_leader_in_dept", [])
    
    # is_leader_in_dept 和 department 是对应的数组
    for i, dept in enumerate(user_depts):
        if dept == dept_id:
            if i < len(is_leader_list):
                return is_leader_list[i] == 1
    
    return False


def get_department_path(dept_id: int) -> List[Dict[str, Any]]:
    """获取部门路径（从根到当前部门）"""
    path = []
    current_id = dept_id
    
    while current_id > 0:
        dept = _DEPARTMENTS.get(current_id)
        if not dept:
            break
        path.insert(0, dept)
        current_id = dept.get("parent_id", 0)
    
    return path


def check_sync_needed() -> bool:
    """检查是否需要同步数据"""
    if not _LAST_SYNC_TIME:
        return True
    
    return datetime.now() - _LAST_SYNC_TIME > SYNC_INTERVAL


def get_org_stats() -> Dict[str, Any]:
    """获取组织架构统计信息"""
    return {
        "departments_count": len(_DEPARTMENTS),
        "users_count": len(_USERS),
        "last_sync_time": _LAST_SYNC_TIME.isoformat() if _LAST_SYNC_TIME else None,
        "sync_interval_hours": SYNC_INTERVAL.total_seconds() / 3600,
        "need_sync": check_sync_needed()
    }


def clear_cache():
    """清空缓存（仅用于测试）"""
    global _LAST_SYNC_TIME
    _ACCESS_TOKEN_CACHE.clear()
    _DEPARTMENTS.clear()
    _USERS.clear()
    _USER_DEPT_MAP.clear()
    _DEPT_USERS_MAP.clear()
    _LAST_SYNC_TIME = None
