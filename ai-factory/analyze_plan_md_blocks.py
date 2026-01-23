from __future__ import annotations

"""分析《实施计划和记录.md》中的记录数量和重复情况。

记录起点规则（OR 关系）：
- 行匹配 "## 📝 笔记 - ..."；
- 或者行以 3 个及以上连续等号开头，例如 "===", "===="。

去重规则：
- 优先使用 SectionID 作为 key (sec:<id>)；
- 若无 SectionID，则使用 note_datetime + 首行正文 作为 key；
- 若连时间和正文都取不到，则用内容 hash 作为 key。

脚本只读文件, 不修改任何内容, 打印:
- total_blocks
- unique_blocks
- duplicate_blocks
"""

from pathlib import Path
import hashlib
import re

ROOT = Path(__file__).resolve().parent
SOURCE_MD = ROOT / "实施计划和记录.md"


def main() -> None:
    if not SOURCE_MD.exists():
        print(f"源文件不存在: {SOURCE_MD}")
        return

    text = SOURCE_MD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    n = len(lines)

    header_pat = re.compile(r"^##\s*📝\s*笔记\s*-\s*(.+)$")

    starts: list[int] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if header_pat.match(s):
            starts.append(i)
        elif s.startswith("===") and set(s) <= {"=", "-"}:  # 容忍 === / ===- 这类分隔
            starts.append(i)

    if not starts:
        print("未找到任何记录起点。")
        return

    # 构造 block 列表
    blocks: list[tuple[int, int, list[str]]] = []
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else n
        blocks.append((s, e, lines[s:e]))

    def block_key(block_lines: list[str]) -> str:
        section_id: str | None = None
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

    keys: list[str] = []
    for _, _, bl in blocks:
        keys.append(block_key(bl))

    unique_map: dict[str, int] = {}
    for idx, k in enumerate(keys):
        unique_map[k] = idx  # 默认保留最后一次

    total_blocks = len(blocks)
    unique_blocks = len(unique_map)
    duplicate_blocks = total_blocks - unique_blocks

    print(f"total_blocks: {total_blocks}")
    print(f"unique_blocks: {unique_blocks}")
    print(f"duplicate_blocks: {duplicate_blocks}")


if __name__ == "__main__":
    main()
