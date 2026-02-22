import os
import time
from typing import Optional
from opencode_client import create_opencode_client, OpenCodeClient
from md_writer import create_md_writer, MDWriter


# 配置 DeepSeek API
os.environ["OPENAI_API_KEY"] = os.getenv("DEEPSEEK_API_KEY", "your-deepseek-key")
os.environ["OPENAI_API_BASE"] = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")

AUTO_GEN_AVAILABLE = False


class AgentA:
    """Agent A - 负责指令梳理和调度"""

    def __init__(
        self,
        opencode_url: str = "http://localhost:4096",
        md_file_path: Optional[str] = None
    ):
        self.opencode_client = create_opencode_client()
        self.md_writer = create_md_writer(md_file_path)
        self.current_session_id: Optional[str] = None

    def refine_instruction(self, user_input: str) -> str:
        """使用 Agent A 梳理指令（通过简单规则）"""
        return self.refine_instruction_simple(user_input)

    def refine_instruction_simple(self, user_input: str) -> str:
        """简单规则梳理指令（备用方案，不依赖 LLM）"""
        refined = user_input.strip()

        replacements = {
            "帮我查一下": "查询",
            "帮我看一下": "查看",
            "那个": "",
            "能不能": "",
            "是否可以": "",
        }

        for old, new in replacements.items():
            refined = refined.replace(old, new)

        refined = " ".join(refined.split())

        if not refined.endswith(("？", "?", "。")):
            refined = refined + "？"

        return refined

    def execute(self, user_input: str, directory: str = "/root/ai-factory/documents/PM", new_session: bool = True) -> dict:
        """执行完整流程：用户输入 → 梳理 → 调用 B → 写 MD
        new_session: 是否创建新 session，False 时复用已有 session
        """
        start_time = time.time()

        # Step 1: 梳理指令
        try:
            refined_input = self.refine_instruction(user_input)
        except Exception as e:
            print(f"LLM 梳理失败，使用简单规则: {e}")
            refined_input = self.refine_instruction_simple(user_input)

        # Step 2: 调用 Agent B (OpenCode)，带上 cd 指令切换目录
        session_id = ""
        try:
            # 在消息前加上 cd 指令切换到指定目录
            full_message = f"cd {directory} && {refined_input}"
            result = self.opencode_client.call(
                message=full_message,
                title=f"User: {user_input[:30]}",
                new_session=new_session
            )
            self.current_session_id = result["session_id"]
            agent_b_result = self.opencode_client.get_last_response_text(
                session_id=result["session_id"]
            )
            session_id = result.get("session_id", "")
        except Exception as e:
            agent_b_result = f"调用失败: {str(e)}"

        # Step 3: 计算耗时
        duration = time.time() - start_time

        # Step 4: 写入 MD
        timestamp = self.md_writer.append(
            user_input=user_input,
            refined_input=refined_input,
            agent_b_result=agent_b_result,
            duration_seconds=duration,
            session_id=session_id
        )

        return {
            "success": True,
            "user_input": user_input,
            "refined_input": refined_input,
            "agent_b_result": agent_b_result,
            "duration_seconds": duration,
            "timestamp": timestamp,
            "session_id": session_id
        }

    def get_current_session_id(self) -> Optional[str]:
        """获取当前 session ID"""
        return self.current_session_id


def create_agent_a(
    opencode_url: str = "http://localhost:4096",
    md_file_path: Optional[str] = None
) -> AgentA:
    """工厂函数：创建 Agent A"""
    return AgentA(opencode_url=opencode_url, md_file_path=md_file_path)


if __name__ == "__main__":
    agent = create_agent_a()
    result = agent.execute("帮我查一下有几个git仓库")
    print(f"结果: {result['agent_b_result']}")
    print(f"耗时: {result['duration_seconds']:.1f}秒")
