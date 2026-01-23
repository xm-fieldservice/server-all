"""
企业微信处理器包。

此模块导入所有处理器，使其自动注册到全局注册表。
"""

# 导入 note_bot 和 qa_bot，触发装饰器注册
from . import note_bot, qa_bot

# 可选：导出已注册的处理器，便于调试
__all__ = ["note_bot", "qa_bot"]