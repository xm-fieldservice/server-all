from __future__ import annotations

"""适配模块：为 ai_factory.integrations.entries_ingest 提供向量化相关函数。

原始实现位于项目根目录的 `vectorize_entries_with_ollama.py`，
这里通过简单转发的方式，提供同名函数：
- _build_embedding_text
- call_ollama_embedding
- upsert_entry_embedding

这样可以兼容 `from ai_factory.vectorize_entries_with_ollama import ...` 的导入路径，
而不改变原有脚本的行为。
"""

from typing import Any, Dict, List
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.append(str(_ROOT))

# 导入根目录下的实现模块
import vectorize_entries_with_ollama as _impl  # type: ignore[import-not-found]


def _build_embedding_text(entry: Dict[str, Any]) -> str:
    return _impl._build_embedding_text(entry)


def call_ollama_embedding(text: str) -> List[float]:
    return _impl.call_ollama_embedding(text)


def upsert_entry_embedding(entry: Dict[str, Any], embedding: List[float]) -> None:
    return _impl.upsert_entry_embedding(entry, embedding)
