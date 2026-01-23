"""
工人-客服群聊系统

功能：
- 工人只能看到自己和客服的对话
- 客服可以看到所有工人的对话
- 客服可以选择回复特定工人
- 集成企业微信组织架构和权限
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from enum import Enum

try:
    from . import wecom_org
except ImportError:
    wecom_org = None


class UserRole(str, Enum):
    """用户角色"""
    WORKER = "worker"  # 工人
    CUSTOMER_SERVICE = "customer_service"  # 客服


# 全局数据存储（生产环境应使用数据库）
USERS: Dict[str, Dict[str, Any]] = {}  # userid -> user_info
GROUP_MESSAGES: List[Dict[str, Any]] = []  # 所有群消息
GROUP_CONVERSATIONS: Dict[str, Dict[str, Any]] = {}  # worker_id -> conversation_info


def register_user(
    user_id: str,
    name: str,
    role: UserRole,
    department_ids: Optional[List[int]] = None,
    **extra_info
) -> Dict[str, Any]:
    """注册用户
    
    Args:
        user_id: 用户ID
        name: 用户姓名
        role: 用户角色（worker/customer_service）
        department_ids: 所属部门ID列表
        **extra_info: 额外信息
        
    Returns:
        用户信息
    """
    # 如果启用了组织架构，先从企业微信同步用户信息
    if wecom_org:
        try:
            wecom_user = wecom_org.get_user_detail(user_id)
            if wecom_user:
                name = wecom_user["name"]
                department_ids = wecom_user.get("department", [])
                extra_info.update({
                    "mobile": wecom_user.get("mobile"),
                    "email": wecom_user.get("email"),
                    "position": wecom_user.get("position"),
                    "avatar": wecom_user.get("avatar"),
                    "status": wecom_user.get("status"),
                })
        except Exception as e:
            print(f"[Warning] 从企业微信同步用户信息失败: {e}")
    
    user_info = {
        "user_id": user_id,
        "name": name,
        "role": role,
        "department_ids": department_ids or [],
        "created_at": datetime.utcnow().isoformat(),
        **extra_info
    }
    USERS[user_id] = user_info
    return user_info


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """获取用户信息"""
    return USERS.get(user_id)


def get_user_role(user_id: str) -> Optional[UserRole]:
    """获取用户角色"""
    user = USERS.get(user_id)
    if user:
        return UserRole(user["role"])
    return None


def send_group_message(
    from_user_id: str,
    content: str,
    to_user_id: Optional[str] = None
) -> Dict[str, Any]:
    """发送群消息
    
    Args:
        from_user_id: 发送者ID
        content: 消息内容
        to_user_id: 接收者ID（可选，用于客服回复特定工人）
        
    Returns:
        消息信息和路由结果
    """
    from_user = USERS.get(from_user_id)
    if not from_user:
        raise ValueError(f"用户 {from_user_id} 不存在")
    
    from_role = UserRole(from_user["role"])
    ts = datetime.utcnow().isoformat()
    
    # 创建消息
    message = {
        "id": len(GROUP_MESSAGES) + 1,
        "from_user_id": from_user_id,
        "from_user_name": from_user["name"],
        "from_role": from_role,
        "to_user_id": to_user_id,  # 如果是客服回复，指定工人ID
        "content": content,
        "timestamp": ts,
    }
    
    GROUP_MESSAGES.append(message)
    
    # 更新会话信息
    if from_role == UserRole.WORKER:
        # 工人发消息，更新该工人的会话
        conversation_id = f"worker:{from_user_id}"
        _update_conversation(conversation_id, from_user_id, message)
    elif from_role == UserRole.CUSTOMER_SERVICE and to_user_id:
        # 客服回复特定工人
        conversation_id = f"worker:{to_user_id}"
        _update_conversation(conversation_id, to_user_id, message)
    
    # 确定消息路由
    routes = _route_message(message)
    
    return {
        "message": message,
        "routes": routes,
        "conversation_id": conversation_id if from_role == UserRole.WORKER or to_user_id else None
    }


def _update_conversation(
    conversation_id: str,
    worker_id: str,
    message: Dict[str, Any]
):
    """更新会话信息"""
    if conversation_id not in GROUP_CONVERSATIONS:
        worker = USERS.get(worker_id)
        GROUP_CONVERSATIONS[conversation_id] = {
            "conversation_id": conversation_id,
            "worker_id": worker_id,
            "worker_name": worker["name"] if worker else worker_id,
            "created_at": message["timestamp"],
            "message_count": 0,
            "unread_count_worker": 0,
            "unread_count_cs": 0,
        }
    
    conv = GROUP_CONVERSATIONS[conversation_id]
    conv["last_message"] = message["content"]
    conv["last_message_time"] = message["timestamp"]
    conv["message_count"] += 1
    
    # 更新未读数
    if message["from_role"] == UserRole.WORKER:
        conv["unread_count_cs"] = conv.get("unread_count_cs", 0) + 1
    else:
        conv["unread_count_worker"] = conv.get("unread_count_worker", 0) + 1


def _route_message(message: Dict[str, Any]) -> List[str]:
    """确定消息路由（哪些用户应该收到这条消息）
    
    规则：
    - 工人发的消息：所有客服可见
    - 客服回复工人：该工人可见 + 所有客服可见
    
    Returns:
        应该接收消息的用户ID列表
    """
    routes = []
    from_role = message["from_role"]
    
    if from_role == UserRole.WORKER:
        # 工人发消息：路由给所有客服
        for user_id, user in USERS.items():
            if user["role"] == UserRole.CUSTOMER_SERVICE:
                routes.append(user_id)
    
    elif from_role == UserRole.CUSTOMER_SERVICE:
        # 客服发消息
        if message["to_user_id"]:
            # 回复特定工人：路由给该工人 + 所有客服
            routes.append(message["to_user_id"])
            for user_id, user in USERS.items():
                if user["role"] == UserRole.CUSTOMER_SERVICE:
                    routes.append(user_id)
    
    return list(set(routes))  # 去重


def get_messages_for_user(
    user_id: str,
    conversation_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """获取用户可见的消息
    
    Args:
        user_id: 用户ID
        conversation_id: 会话ID（可选，客服查看特定工人的对话时使用）
        
    Returns:
        用户可见的消息列表
    """
    user = USERS.get(user_id)
    if not user:
        return []
    
    role = UserRole(user["role"])
    visible_messages = []
    
    if role == UserRole.WORKER:
        # 工人只能看到自己发的消息和客服回复自己的消息
        for msg in GROUP_MESSAGES:
            # 工人自己发的消息
            if msg["from_user_id"] == user_id:
                visible_messages.append(msg)
            # 客服回复给这个工人的消息
            elif msg["from_role"] == UserRole.CUSTOMER_SERVICE and msg["to_user_id"] == user_id:
                visible_messages.append(msg)
    
    elif role == UserRole.CUSTOMER_SERVICE:
        if conversation_id:
            # 客服查看特定工人的对话
            worker_id = conversation_id.replace("worker:", "")
            for msg in GROUP_MESSAGES:
                # 该工人发的消息
                if msg["from_user_id"] == worker_id:
                    visible_messages.append(msg)
                # 客服回复该工人的消息
                elif msg["to_user_id"] == worker_id:
                    visible_messages.append(msg)
        else:
            # 客服看所有消息（用于列表展示）
            visible_messages = GROUP_MESSAGES.copy()
    
    return visible_messages


def get_conversations_for_cs() -> List[Dict[str, Any]]:
    """获取客服的对话列表（按最后消息时间排序）"""
    conversations = list(GROUP_CONVERSATIONS.values())
    conversations.sort(
        key=lambda x: x.get("last_message_time", ""),
        reverse=True
    )
    return conversations


def mark_conversation_read(conversation_id: str, user_id: str):
    """标记会话为已读
    
    Args:
        conversation_id: 会话ID
        user_id: 用户ID
    """
    conv = GROUP_CONVERSATIONS.get(conversation_id)
    if not conv:
        return
    
    user = USERS.get(user_id)
    if not user:
        return
    
    role = UserRole(user["role"])
    
    if role == UserRole.WORKER:
        conv["unread_count_worker"] = 0
    elif role == UserRole.CUSTOMER_SERVICE:
        conv["unread_count_cs"] = 0


def get_all_users() -> Dict[str, List[Dict[str, Any]]]:
    """获取所有用户，按角色分组"""
    workers = []
    customer_services = []
    
    for user in USERS.values():
        if user["role"] == UserRole.WORKER:
            workers.append(user)
        elif user["role"] == UserRole.CUSTOMER_SERVICE:
            customer_services.append(user)
    
    return {
        "workers": workers,
        "customer_services": customer_services
    }


def clear_all_data():
    """清空所有数据（仅用于测试）"""
    USERS.clear()
    GROUP_MESSAGES.clear()
    GROUP_CONVERSATIONS.clear()
