"""清理 ai-factory/autogen_repo 中与 docs/autogen_repo 完全重复的内容。

支持两种模式：

1. list（默认）
   - 遍历 docs/autogen_repo 下的所有文件；
   - 在 autogen_repo 中查找相同相对路径的文件；
   - 若两个文件内容完全一致（SHA256），则将 autogen_repo 中的路径记录到
     scripts/autogen_repo_dups.txt，但**不做任何删除**。

   用法示例：

       cd D:/AI/ai-factory
       python scripts/clean_autogen_repo.py
       # 或显式：
       python scripts/clean_autogen_repo.py list

2. clean
   - 读取 scripts/autogen_repo_dups.txt 中的路径；
   - 逐个删除这些文件（仅工作区），然后清理 autogen_repo 中的空目录；
   - 适用于你已经根据 dups 清单完成 git rm --cached 之后。

   用法示例：

       cd D:/AI/ai-factory
       python scripts/clean_autogen_repo.py clean

无论哪种模式，都会保证：
- 仅针对 docs/autogen_repo 与 autogen_repo 之间“路径相同且内容完全一致”的文件；
- 其它任何只存在于 autogen_repo 或内容不同的文件一律保留。
"""

import hashlib
import sys
from pathlib import Path


def sha256_of_file(path: Path) -> str:
    """计算文件的 SHA256 哈希。"""

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def find_duplicates(docs_root: Path, old_root: Path, dups_file: Path) -> int:
    """扫描重复文件, 将 autogen_repo 中的路径写入文本清单, 返回重复数量。

    不执行删除, 仅记录: 相对 repo_root 的路径列表, 便于后续 git rm --cached 使用。
    """

    repo_root = docs_root.parents[1]

    all_docs_files = list(docs_root.rglob("*"))
    docs_files = [p for p in all_docs_files if p.is_file()]

    print(f"待比对文件数: {len(docs_files)}")

    duplicates: list[str] = []

    for src in docs_files:
        rel = src.relative_to(docs_root)
        candidate = old_root / rel

        if not candidate.exists() or not candidate.is_file():
            continue

        try:
            h1 = sha256_of_file(src)
            h2 = sha256_of_file(candidate)
        except Exception as e:
            print(f"[WARN] 计算哈希失败, 跳过: {candidate} -> {e}")
            continue

        if h1 == h2:
            rel_to_repo = candidate.relative_to(repo_root)
            path_str = str(rel_to_repo).replace("\\", "/")
            print(f"发现重复文件: {path_str}")
            duplicates.append(path_str)

    if duplicates:
        try:
            dups_file.parent.mkdir(parents=True, exist_ok=True)
            dups_file.write_text("\n".join(duplicates), encoding="utf-8")
            print(f"重复文件清单已写入: {dups_file} (共 {len(duplicates)} 条)")
        except Exception as e:
            print(f"[ERROR] 写入重复文件清单失败: {e}")
    else:
        print("未发现任何重复文件。")

    return len(duplicates)


def clean_duplicates(old_root: Path, dups_file: Path) -> tuple[int, int]:
    """根据清单删除重复文件并清理空目录, 返回 (删除文件数, 删除目录数)。"""

    repo_root = old_root.parents[0]
    if not dups_file.exists():
        print(f"[ERROR] 找不到重复文件清单: {dups_file}")
        return 0, 0

    lines = [l.strip() for l in dups_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    deleted = 0

    print(f"开始根据清单删除重复文件, 条目数: {len(lines)}")

    for rel in lines:
        candidate = repo_root / rel
        if candidate.exists() and candidate.is_file():
            try:
                print(f"删除重复文件: {candidate}")
                candidate.unlink()
                deleted += 1
            except Exception as e:
                print(f"[ERROR] 删除文件失败: {candidate} -> {e}")
        else:
            print(f"[WARN] 清单中的路径不存在或不是文件, 跳过: {candidate}")

    # 清理空目录（从深到浅）
    removed_dirs = 0
    all_dirs = [p for p in old_root.rglob("*") if p.is_dir()]
    all_dirs.sort(key=lambda p: len(str(p)), reverse=True)

    for d in all_dirs:
        try:
            if not any(d.iterdir()):
                print(f"删除空目录: {d}")
                d.rmdir()
                removed_dirs += 1
        except Exception as e:
            print(f"[WARN] 删除目录失败: {d} -> {e}")

    return deleted, removed_dirs


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    docs_root = repo_root / "docs" / "autogen_repo"
    old_root = repo_root / "autogen_repo"

    print(f"docs 知识库目录 : {docs_root}")
    print(f"old  旧仓库目录 : {old_root}")

    if not docs_root.exists() or not old_root.exists():
        print("[ERROR] 路径不存在，请检查 docs/autogen_repo 与 autogen_repo 是否存在。")
        return 1

    # 模式解析: 默认 list, 可显式传入 list/clean
    mode = (sys.argv[1].strip().lower() if len(sys.argv) >= 2 else "list")
    dups_file = repo_root / "scripts" / "autogen_repo_dups.txt"

    if mode not in {"list", "clean"}:
        print(f"[ERROR] 不支持的模式: {mode}, 仅支持 list / clean")
        return 1

    if mode == "list":
        print("运行模式: list (仅生成重复文件清单, 不删除任何文件)")
        count = find_duplicates(docs_root, old_root, dups_file)
        print("done. 可查看清单并根据需要执行: git rm --cached <路径>。")
        return 0 if count >= 0 else 1

    # clean 模式
    print("运行模式: clean (根据清单删除重复文件并清理空目录)")
    deleted, removed_dirs = clean_duplicates(old_root, dups_file)
    print(f"重复文件删除总数: {deleted}")
    print(f"空目录删除总数: {removed_dirs}")
    print("清理完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
