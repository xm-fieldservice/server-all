"""
Memory0 配置模块

集中管理 Memory0 的配置参数，支持按 Agent/场景配置不同策略。

基于设计文档：Agent记忆系统详细设计与施工文档.md - 9.3 配置集中化
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum


class Memory0Profile(str, Enum):
    """Memory0 策略档位"""
    CONSERVATIVE = "conservative"  # 保守型：倾向 NEW + DUPLICATE，少 OVERRIDE
    AGGRESSIVE = "aggressive"      # 激进型：更多 OVERRIDE，快速更新规则
    OBSERVANT = "observant"        # 观察型：先记录为 NEW + 冲突标记，待人工/外循环确认


@dataclass
class Memory0Config:
    """Memory0 配置参数"""
    
    # 相似度阈值
    sim_threshold_low: float = 0.70      # 低相似度阈值，低于此值判定为 NEW
    sim_threshold_high: float = 0.85     # 高相似度阈值，高于此值判定为 DUPLICATE/UPDATE/OVERRIDE
    
    # 检索参数
    top_k_candidates: int = 10         # 检索候选数量
    
    # 冲突信号词列表
    conflict_keywords: List[str] = field(default_factory=lambda: [
        "不再", "废弃", "改为", "新版本是", "替换为", "更新为",
        "作废", "取消", "撤销", "推翻", "重新定义"
    ])
    
    # UPDATE 模式选择
    update_mode: str = "lightweight"  # UPDATE 模式：lightweight(轻量)/merge(合并)/extend(扩展)
    
    # 权重更新参数
    importance_new: float = 1.0         # NEW 条目的初始 importance
    importance_update: float = 1.1      # UPDATE 时提升 importance 的因子
    importance_override: float = 1.5    # OVERRIDE 时新条目的 importance
    
    # 重复判断参数
    duplicate_length_ratio: float = 0.9  # 内容长度差异阈值
    duplicate_prefix_len: int = 100      # 前缀比较长度
    
    # 是否允许自动内容合并
    enable_auto_merge: bool = False    # 是否允许自动合并内容（UPDATE 模式 2）
    
    # 是否记录冲突标记
    enable_conflict_marking: bool = True  # 是否在 extra_meta 中记录冲突标记


@dataclass
class AgentMemoryConfig:
    """Agent 记忆配置"""
    
    # Agent 基本信息
    agent_id: str
    agent_name: str
    profile: Memory0Profile = Memory0Profile.CONSERVATIVE
    
    # 记忆策略配置
    enable_section: bool = True           # 是否启用 Section
    enable_memory0: bool = True          # 是否启用 Memory0
    enable_async_memory0: bool = False   # 是否启用异步 Memory0 处理
    
    # Section 触发配置
    section_trigger_message_count: Optional[int] = None  # 基于消息数量的触发阈值
    section_trigger_time_interval: Optional[int] = None  # 基于时间间隔的触发阈值（秒）
    
    # Memory0 配置
    memory0_config: Memory0Config = field(default_factory=Memory0Config)
    
    # 场景标签模板
    scene_tag_templates: Dict[str, List[str]] = field(default_factory=dict)
    
    # 空间类型默认值
    default_space_type: str = "note"
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


# 全局默认配置
DEFAULT_CONFIG = Memory0Config()

# 预定义的 Memory0 配置档位
MEMORY0_PROFILES = {
    Memory0Profile.CONSERVATIVE: Memory0Config(
        sim_threshold_low=0.70,
        sim_threshold_high=0.90,
        top_k_candidates=10,
        conflict_keywords=[
            "不再", "废弃", "改为", "新版本是", "替换为", "更新为",
            "作废", "取消", "撤销", "推翻", "重新定义"
        ],
        update_mode="lightweight",
        importance_new=1.0,
        importance_update=1.05,
        importance_override=1.3,
        duplicate_length_ratio=0.95,
        duplicate_prefix_len=100,
        enable_auto_merge=False,
        enable_conflict_marking=True
    ),
    
    Memory0Profile.AGGRESSIVE: Memory0Config(
        sim_threshold_low=0.65,
        sim_threshold_high=0.80,
        top_k_candidates=15,
        conflict_keywords=[
            "不再", "废弃", "改为", "新版本是", "替换为", "更新为",
            "作废", "取消", "撤销", "推翻", "重新定义",
            "调整", "修改", "变更"
        ],
        update_mode="merge",
        importance_new=1.0,
        importance_update=1.15,
        importance_override=1.8,
        duplicate_length_ratio=0.85,
        duplicate_prefix_len=80,
        enable_auto_merge=True,
        enable_conflict_marking=True
    ),
    
    Memory0Profile.OBSERVANT: Memory0Config(
        sim_threshold_low=0.75,
        sim_threshold_high=0.85,
        top_k_candidates=10,
        conflict_keywords=[
            "不再", "废弃", "改为", "新版本是", "替换为", "更新为",
            "作废", "取消", "撤销", "推翻", "重新定义"
        ],
        update_mode="lightweight",
        importance_new=1.0,
        importance_update=1.1,
        importance_override=1.5,
        duplicate_length_ratio=0.9,
        duplicate_prefix_len=100,
        enable_auto_merge=False,
        enable_conflict_marking=True
    )
}


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        """初始化配置管理器"""
        self._agent_configs: Dict[str, AgentMemoryConfig] = {}
        self._default_config: AgentMemoryConfig = AgentMemoryConfig(
            agent_id="default",
            agent_name="Default Agent",
            profile=Memory0Profile.CONSERVATIVE
        )
    
    def register_agent_config(self, config: AgentMemoryConfig) -> None:
        """注册 Agent 配置
        
        Args:
            config: Agent 记忆配置
        """
        self._agent_configs[config.agent_id] = config
    
    def get_agent_config(self, agent_id: str) -> AgentMemoryConfig:
        """获取 Agent 配置
        
        Args:
            agent_id: Agent ID
            
        Returns:
            AgentMemoryConfig: Agent 配置，如果未注册则返回默认配置
        """
        return self._agent_configs.get(agent_id, self._default_config)
    
    def get_memory0_config(self, agent_id: str) -> Memory0Config:
        """获取 Agent 的 Memory0 配置
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Memory0Config: Memory0 配置
        """
        agent_config = self.get_agent_config(agent_id)
        return agent_config.memory0_config
    
    def update_agent_profile(self, agent_id: str, profile: Memory0Profile) -> None:
        """更新 Agent 的 Memory0 策略档位
        
        Args:
            agent_id: Agent ID
            profile: Memory0 策略档位
        """
        if agent_id in self._agent_configs:
            self._agent_configs[agent_id].profile = profile
            # 应用预定义的配置档位
            self._agent_configs[agent_id].memory0_config = MEMORY0_PROFILES[profile]
    
    def update_memory0_config(
        self,
        agent_id: str,
        **kwargs
    ) -> None:
        """更新 Agent 的 Memory0 配置参数
        
        Args:
            agent_id: Agent ID
            **kwargs: 要更新的配置参数
        """
        if agent_id not in self._agent_configs:
            # 如果 Agent 未注册，先注册默认配置
            self.register_agent_config(AgentMemoryConfig(
                agent_id=agent_id,
                agent_name=f"Agent {agent_id}",
                profile=Memory0Profile.CONSERVATIVE
            ))
        
        # 更新指定的配置参数
        config = self._agent_configs[agent_id].memory0_config
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
    
    def list_agent_configs(self) -> List[AgentMemoryConfig]:
        """列出所有已注册的 Agent 配置
        
        Returns:
            List[AgentMemoryConfig]: Agent 配置列表
        """
        return list(self._agent_configs.values())
    
    def remove_agent_config(self, agent_id: str) -> bool:
        """移除 Agent 配置
        
        Args:
            agent_id: Agent ID
            
        Returns:
            bool: 是否成功移除
        """
        if agent_id in self._agent_configs:
            del self._agent_configs[agent_id]
            return True
        return False
    
    def get_default_config(self) -> AgentMemoryConfig:
        """获取默认配置
        
        Returns:
            AgentMemoryConfig: 默认配置
        """
        return self._default_config


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例
    
    Returns:
        ConfigManager: 配置管理器实例
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def register_default_agents() -> None:
    """注册一些默认的 Agent 配置"""
    manager = get_config_manager()
    
    # 注册默认 Agent
    manager.register_agent_config(AgentMemoryConfig(
        agent_id="default",
        agent_name="Default Agent",
        profile=Memory0Profile.CONSERVATIVE,
        scene_tag_templates={
            "execution": ["笔记"],
            "planning": ["项目"]
        },
        default_space_type="note"
    ))
    
    # 注册项目助手 Agent
    manager.register_agent_config(AgentMemoryConfig(
        agent_id="agent_project",
        agent_name="Project Assistant",
        profile=Memory0Profile.CONSERVATIVE,
        enable_section=True,
        enable_memory0=True,
        section_trigger_message_count=20,
        scene_tag_templates={
            "execution": ["项目", "任务"],
            "planning": ["项目", "计划"]
        },
        default_space_type="note"
    ))
    
    # 注册聊天助手 Agent
    manager.register_agent_config(AgentMemoryConfig(
        agent_id="agent_chat",
        agent_name="Chat Assistant",
        profile=Memory0Profile.AGGRESSIVE,
        enable_section=True,
        enable_memory0=True,
        section_trigger_message_count=10,
        scene_tag_templates={
            "execution": ["对话"]
        },
        default_space_type="note"
    ))


# 模块初始化时注册默认 Agent
register_default_agents()


__all__ = [
    # 枚举类
    "Memory0Profile",
    
    # 数据类
    "Memory0Config",
    "AgentMemoryConfig",
    
    # 配置管理器
    "ConfigManager",
    "get_config_manager",
    "register_default_agents",
    
    # 预定义配置
    "DEFAULT_CONFIG",
    "MEMORY0_PROFILES",
]
