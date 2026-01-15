from __future__ import annotations

"""从《实施计划和记录.md》中抽取“去重+过滤测试”后的正式工作记录，输出为《规整工作记录.md》。

规则摘要：
- 记录起点（OR 关系）：
  - 行匹配 "## 📝 笔记 - ..."；
  - 或行以 3 个及以上连续等号开头（如 "===", "====", "===----"）。
- 去重：
  - 优先使用 SectionID=... 作为 key (sec:<id>)；
  - 若无 SectionID，则使用 note_datetime + 首行正文 作为 key；
  - 若连时间和正文都取不到，则用内容 hash 作为 key；
  - 对同一 key，只保留“在原文件中最后出现”的那一块。
- 过滤测试/占位记录：
  - 若整块文本中包含以下任一子串，则视为测试/占位记录，不导出：
    - "测试样例"
    - "测试输入（不作为真实笔记）"
    - "测试输入"
    - "测试文本样例"
    - "不作为真实笔记"

脚本只读《实施计划和记录.md》，在同目录生成《规整工作记录.md》，原文不改动。
"""

from pathlib import Path
import hashlib
import re
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent
SOURCE_MD = ROOT / "实施计划和记录.md"
TARGET_MD = ROOT / "规整工作记录.md"

TEST_KEYWORDS = [
    "测试样例",
    "测试输入（不作为真实笔记）",
    "测试输入",
    "测试文本样例",
    "不作为真实笔记",
]


def split_blocks(text: str) -> Tuple[List[Tuple[int, int, List[str]]], re.Pattern[str]]:
    """按起点规则切分为若干块，返回 (blocks, header_pattern)。"""

    lines = text.splitlines(keepends=True)
    n = len(lines)

    header_pat = re.compile(r"^##\s*📝\s*笔记\s*-\s*(.+)$")
    starts: List[int] = []

    for i, line in enumerate(lines):
        s = line.strip()
        if header_pat.match(s):
            starts.append(i)
        elif s.startswith("===") and set(s) <= {"=", "-"}:
            starts.append(i)

    if not starts:
        return [], header_pat

    blocks: List[Tuple[int, int, List[str]]] = []
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else n
        blocks.append((s, e, lines[s:e]))

    return blocks, header_pat


def make_block_key(block_lines: List[str], header_pat: re.Pattern[str]) -> str:
    """生成用于去重的 key。"""

    section_id = None
    for bl in block_lines:
        if "SectionID=" in bl:
            m = re.search(r"SectionID=([^;\s]+)", bl)
            if m:
                section_id = m.group(1).strip()
                break
    if section_id:
        return "sec:" + section_id

    note_dt = ""
    for bl in block_lines:
        m = header_pat.match(bl.strip())
        if m:
            note_dt = m.group(1).strip()
            break

    title_hint = ""
    for bl in block_lines:
        s = bl.strip()
        if not s:
            continue
        if s.startswith("##") or s.startswith("===") or s.startswith("标签："):
            continue
        title_hint = s
        break

    if not note_dt and not title_hint:
        h = hashlib.sha1("".join(block_lines).encode("utf-8")).hexdigest()[:8]
        return "hash:" + h

    return f"ts:{note_dt}|{title_hint[:50]}"


def is_test_like(block_text: str) -> bool:
    """判断该块是否属于测试/占位记录。"""

    for kw in TEST_KEYWORDS:
        if kw in block_text:
            return True
    return False


def main() -> None:
    if not SOURCE_MD.exists():
        print(f"源文件不存在: {SOURCE_MD}")
        return

    text = SOURCE_MD.read_text(encoding="utf-8")
    blocks, header_pat = split_blocks(text)

    if not blocks:
        print("未在文档中找到任何记录块，未生成输出文件。")
        return

    # 去重：同一 key 只保留最后一次出现
    key_to_block: dict[str, Tuple[int, int, List[str]]] = {}
    for start, end, bl in blocks:
        key = make_block_key(bl, header_pat)
        key_to_block[key] = (start, end, bl)

    dedup_blocks = list(key_to_block.values())
    # 按在原文中的起始行号排序
    dedup_blocks.sort(key=lambda x: x[0])

    kept_blocks: List[List[str]] = []
    dropped_test = 0

    for start, end, bl in dedup_blocks:
        block_text = "".join(bl)
        if is_test_like(block_text):
            dropped_test += 1
            continue
        kept_blocks.append(bl)

    if not kept_blocks:
        print("所有记录块都被测试/占位规则过滤掉，未生成输出文件。")
        return

    out_lines: List[str] = []
    out_lines.append("<!-- 该文件由 export_clean_records_md.py 自动生成，来源：实施计划和记录.md -->\n")
    out_lines.append("<!-- 规则：去重 (SectionID/时间+首行) + 过滤测试样例/占位记录，仅保留正式工作记录。 -->\n\n")

    for idx, bl in enumerate(kept_blocks, start=1):
        out_lines.append(f"<!-- 记录 #{idx} 开始 -->\n")
        out_lines.extend(bl)
        if not bl[-1].endswith("\n"):
            out_lines.append("\n")
        out_lines.append("\n\n")

    TARGET_MD.write_text("".join(out_lines), encoding="utf-8")

    print(f"总块数: {len(blocks)}")
    print(f"去重后块数: {len(dedup_blocks)}")
    print(f"过滤掉测试/占位块数: {dropped_test}")
    print(f"最终保留正式工作记录数: {len(kept_blocks)}")
    print(f"输出文件: {TARGET_MD}")


if __name__ == "__main__":
    main()
