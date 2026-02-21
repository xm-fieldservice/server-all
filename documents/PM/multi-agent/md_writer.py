import os
from datetime import datetime
from typing import Optional
from pathlib import Path


class MDWriter:
    """Markdown 文档写入器"""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """确保文件存在，如果不存在则创建"""
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_file()

    def _init_file(self):
        """初始化文件头部"""
        header = f"""# 对话记录

> 自动生成，请勿手动修改

---
"""
        self.file_path.write_text(header, encoding="utf-8")

    def append(
        self,
        user_input: str,
        refined_input: str,
        agent_b_result: str,
        duration_seconds: Optional[float] = None
    ) -> str:
        """追加对话记录"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_only = datetime.now().strftime("%Y-%m-%d")

        duration_str = ""
        if duration_seconds is not None:
            duration_str = f"**执行时长**: {duration_seconds:.1f} 秒\n"

        entry = f"""## {date_only} {datetime.now().strftime("%H:%M:%S")}

### 👤 用户指令
```
{user_input}
```

### 🔄 Agent A 梳理后
```
{refined_input}
```

### 🤖 Agent B 返回
```
{agent_b_result}
```

{duration_str}---
"""

        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(entry)

        return timestamp

    def get_recent_entries(self, count: int = 5) -> str:
        """获取最近 N 条记录"""
        if not self.file_path.exists():
            return ""

        content = self.file_path.read_text(encoding="utf-8")
        sections = content.split("## ")

        if len(sections) <= 1:
            return ""

        recent = sections[-count:] if len(sections) > count else sections[1:]
        return "## ".join(recent)


def create_md_writer(file_path: Optional[str] = None) -> MDWriter:
    """工厂函数：创建 MD 写入器"""
    if file_path is None:
        base_dir = Path(__file__).parent
        md_path = base_dir / "logs" / "conversation.md"
        file_path = str(md_path)

    return MDWriter(file_path)


if __name__ == "__main__":
    writer = create_md_writer()
    writer.append(
        user_input="帮我查一下天气",
        refined_input="请查询北京今天的天气情况",
        agent_b_result="北京今天晴转多云，15-25度",
        duration_seconds=3.5
    )
    print("写入成功")
