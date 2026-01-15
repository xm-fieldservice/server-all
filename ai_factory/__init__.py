"""AI 工厂核心包
 
约定：
- agents: 各类 Agent 编排逻辑（autogen / MCP / 任务路由）
- db: 与 Postgres/pgvector/未来图数据库的访问封装
- rag: RAG 流程与向量检索统一接口
- frameworks: 对 langchain / llamaindex / graphrag 等框架的适配层
 
后续具体模块按需逐步实现。
"""

from __future__ import annotations

from pathlib import Path


def _load_project_dotenv() -> None:
    """在首次导入 ai_factory 时尝试加载全局与项目级 .env。

    约定：
    - AI 根目录为 ``D:\AI``（或等价路径），其中包含全局配置文件 ``.env``；
    - 本包位于 ``<ai_root>/ai-factory/ai_factory``；
    - 项目级覆盖配置位于 ``<ai_root>/ai-factory/.env``（可选）；
    - 若未安装 python-dotenv 或文件不存在，则静默忽略。
    """

    try:
        from dotenv import load_dotenv  # type: ignore[import]
    except Exception:
        # 不强制依赖 python-dotenv，缺失时直接跳过。
        return

    pkg_dir = Path(__file__).resolve().parent          # .../ai-factory/ai_factory
    project_root = pkg_dir.parent                      # .../ai-factory
    ai_root = project_root.parent                      # .../AI

    # 1) 全局 D:\AI\.env：作为统一真源，不覆盖已有环境变量
    global_env = ai_root / ".env"
    if global_env.is_file():
        load_dotenv(global_env, override=False)

    # 2) 项目级 D:\AI\ai-factory\.env：仅在需要时做局部覆盖（可选）
    local_env = project_root / ".env"
    if local_env.is_file():
        load_dotenv(local_env, override=True)


_load_project_dotenv()


__all__ = []
