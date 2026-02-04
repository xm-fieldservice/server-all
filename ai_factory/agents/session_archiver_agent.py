"""
会话自动归档SubAgent - SessionArchiverAgent

功能：监听特定关键词（入库、写库、保存、存档），自动将完整会话通过2号通道写入entries

使用方式：
    from ai_factory.agents.session_archiver_agent import SessionArchiverAgent
    
    archiver = SessionArchiverAgent()
    
    # 在每次用户输入后调用
    result = archiver.check_and_archive(
        session_id="session_001",
        user_input="帮我把刚才的对话入库",
        assistant_response="刚才我们讨论了...",
        conversation_history=[...],
        project_code="ai_factory"
    )
"""

import re
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ArchiveResult:
    """归档结果"""
    archived: bool  # 是否触发归档
    entry_id: Optional[str]  # 归档后的entry_id
    trigger_keyword: Optional[str]  # 触发的关键词
    job_id: Optional[str]  # 2号通道返回的job_id
    message: str  # 结果说明


class SessionArchiverAgent:
    """
    会话自动归档Agent
    
    监听关键词：入库、写库、保存、存档
    自动将完整会话内容通过2号通道写入entries
    """
    
    # 归档触发关键词
    TRIGGER_KEYWORDS = [
        "入库", "写库", "保存", "存档", 
        "归档", "记录", "记下来", "存下来",
        "写入数据库", "保存会话", "保存记录"
    ]
    
    def __init__(self, 
                 api_base: str = "http://121.43.126.173:8001",
                 use_local_call: bool = True):
        """
        初始化归档Agent
        
        Args:
            api_base: API基础地址（使用2号通道HTTP API时）
            use_local_call: 是否使用本地函数调用（True: entries_ingest, False: HTTP API）
        """
        self.api_base = api_base
        self.use_local_call = use_local_call
        
        # 编译关键词匹配正则
        self.keyword_patterns = [
            re.compile(rf"\b{re.escape(kw)}\b") 
            for kw in self.TRIGGER_KEYWORDS
        ]
    
    def check_and_archive(self,
                         session_id: str,
                         user_input: str,
                         assistant_response: str,
                         conversation_history: List[Dict[str, Any]],
                         project_code: str = "ai_factory",
                         user_id: str = "ecs-assist-user",
                         section: str = "IDE会话归档",
                         visibility: str = "private") -> ArchiveResult:
        """
        检查是否触发归档，如果是则执行归档
        
        Args:
            session_id: 会话ID
            user_input: 用户当前输入
            assistant_response: 助手当前回复
            conversation_history: 完整会话历史（包含input和output）
            project_code: 项目代码
            user_id: 用户ID
            section: section标识
            visibility: 可见性（private/public）
            
        Returns:
            ArchiveResult: 归档结果
        """
        
        # 1. 检查是否触发归档
        trigger_kw = self._detect_trigger_keyword(user_input)
        
        if not trigger_kw:
            return ArchiveResult(
                archived=False,
                entry_id=None,
                trigger_keyword=None,
                job_id=None,
                message="未检测到归档关键词，跳过归档"
            )
        
        # 2. 构建归档内容
        archived_content = self._build_archive_content(
            session_id, 
            conversation_history,
            user_input,
            assistant_response
        )
        
        # 3. 通过2号通道写入
        try:
            if self.use_local_call:
                entry_id = self._write_via_local(archived_content, project_code, user_id, section, visibility)
                return ArchiveResult(
                    archived=True,
                    entry_id=entry_id,
                    trigger_keyword=trigger_kw,
                    job_id=None,
                    message=f"✓ 会话已通过本地调用归档到entries，Entry ID: {entry_id}"
                )
            else:
                job_id = self._write_via_http_api(archived_content, project_code, user_id, section, visibility)
                return ArchiveResult(
                    archived=True,
                    entry_id=None,
                    trigger_keyword=trigger_kw,
                    job_id=job_id,
                    message=f"✓ 会话已提交到2号通道异步处理，Job ID: {job_id}"
                )
                
        except Exception as e:
            return ArchiveResult(
                archived=False,
                entry_id=None,
                trigger_keyword=trigger_kw,
                job_id=None,
                message=f"✗ 归档失败: {str(e)}"
            )
    
    def _detect_trigger_keyword(self, text: str) -> Optional[str]:
        """检测是否包含归档关键词"""
        text_lower = text.lower()
        
        for i, pattern in enumerate(self.keyword_patterns):
            if pattern.search(text_lower) or self.TRIGGER_KEYWORDS[i] in text:
                return self.TRIGGER_KEYWORDS[i]
        
        return None
    
    def _build_archive_content(self,
                              session_id: str,
                              conversation_history: List[Dict[str, Any]],
                              current_input: str,
                              current_response: str) -> str:
        """构建归档的Markdown内容"""
        
        lines = [
            f"# IDE会话归档 - {session_id}",
            "",
            f"**归档时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**会话ID**: {session_id}",
            "",
            "---",
            "",
            "## 会话内容",
            ""
        ]
        
        # 添加历史会话
        for i, turn in enumerate(conversation_history, 1):
            user_msg = turn.get('input', '') or turn.get('user', '') or turn.get('content', '')
            assistant_msg = turn.get('output', '') or turn.get('assistant', '') or turn.get('response', '')
            
            if user_msg:
                lines.extend([
                    f"### 提问 #{i}",
                    "",
                    user_msg,
                    ""
                ])
            
            if assistant_msg:
                lines.extend([
                    f"**回答 #{i}**:",
                    "",
                    "```",
                    assistant_msg[:500] + "..." if len(assistant_msg) > 500 else assistant_msg,
                    "```",
                    "",
                    "---",
                    ""
                ])
        
        # 添加当前轮次
        if current_input:
            lines.extend([
                f"### 最终提问",
                "",
                current_input,
                ""
            ])
        
        if current_response:
            lines.extend([
                f"**最终回答**:",
                "",
                "```",
                current_response[:500] + "..." if len(current_response) > 500 else current_response,
                "```",
                ""
            ])
        
        # 添加元数据标签行
        lines.extend([
            "",
            f"标签：部门=架构部；规划=会话归档；执行=自动入库；状态=已完成",
            ""
        ])
        
        return "\n".join(lines)
    
    def _write_via_local(self, 
                        content: str, 
                        project_code: str,
                        user_id: str,
                        section: str,
                        visibility: str) -> str:
        """通过本地函数调用写入（1号通道）"""
        
        from ai_factory.integrations.entries_ingest import entries_ingest
        
        payload = {
            "raw_text": content,
            "note_datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "project_code": project_code,
            "user_id": user_id,
            "extra_context": {
                "tags_snapshot": {
                    "department": ["架构部"],
                    "planning": ["会话归档"],
                    "execution": ["自动入库"],
                    "status": ["已完成"]
                }
            },
            "extra_meta": {
                "section": section,
                "section_type": "会话归档",
                "source_system": "ai_factory",
                "visibility": visibility,
                "owner_id": user_id,
                "allow_public_extract": True
            }
        }
        
        result = entries_ingest(payload)
        # entries_ingest 返回 {"entries": [{"entry_id": "xxx", ...}]}
        entries = result.get("entries", [])
        if entries and len(entries) > 0:
            return entries[0].get("entry_id", "unknown")
        return "unknown"
    
    def _write_via_http_api(self,
                           content: str,
                           project_code: str,
                           user_id: str,
                           section: str,
                           visibility: str) -> str:
        """通过HTTP API写入（2号通道）"""
        
        import requests
        
        payload = {
            "task_type": "note",
            "payload": {
                "raw_text": content,
                "note_datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "project_code": project_code,
                "user_id": user_id,
                "extra_context": {
                    "tags_snapshot": {
                        "department": ["架构部"],
                        "planning": ["会话归档"],
                        "execution": ["自动入库"],
                        "status": ["已完成"]
                    }
                },
                "extra_meta": {
                    "section": section,
                    "section_type": "会话归档",
                    "source_system": "ai_factory",
                    "visibility": visibility,
                    "owner_id": user_id,
                    "allow_public_extract": True
                }
            },
            "idempotency_key": f"session_archive_{int(time.time())}_{user_id}"
        }
        
        response = requests.post(
            f"{self.api_base}/access/v1/entries/ingest",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        
        result = response.json()
        if not result.get("ok"):
            raise Exception(f"API调用失败: {result}")
        
        return result.get("job_id")


# IDE集成示例（伪代码）
"""
# 在IDE的主循环中使用：

from ai_factory.agents.session_archiver_agent import SessionArchiverAgent

# 初始化归档Agent
archiver = SessionArchiverAgent(
    api_base="http://121.43.126.173:8001",
    use_local_call=True  # True=本地函数调用，False=HTTP API
)

# 会话历史存储
conversation_history = []

# 主循环
while True:
    # 获取用户输入
    user_input = get_user_input()
    
    # 处理用户请求
    assistant_response = process_user_request(user_input)
    
    # 检查是否需要归档
    result = archiver.check_and_archive(
        session_id=current_session_id,
        user_input=user_input,
        assistant_response=assistant_response,
        conversation_history=conversation_history.copy(),
        project_code="ai_factory",
        user_id="current_user"
    )
    
    if result.archived:
        # 向用户展示归档结果
        print(result.message)
        
        # 如果需要，可以在这里清除会话历史或开始新会话
        if result.trigger_keyword in ["存档", "归档"]:
            conversation_history = []  # 清空历史
    
    # 将当前轮次加入历史
    conversation_history.append({
        "input": user_input,
        "output": assistant_response
    })
    
    # 显示助手回复
    print(assistant_response)
"""
