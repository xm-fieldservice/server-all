from __future__ import annotations

import sys
from pathlib import Path

# 指向 desktop_app 目录
DESKTOP_APP_ROOT = Path(r"D:\AI\desktop_app")
CONFIG_PATH = r"D:\AI\desktop_app\config\agents\ingest_agent.json"


def _ensure_import_run_agent():
    """将 desktop_app 加入 sys.path，导入 run_agent_once。"""
    config_dir = DESKTOP_APP_ROOT / "config"
    if str(config_dir) not in sys.path:
        sys.path.insert(0, str(config_dir))

    import run_agent  # type: ignore
    return run_agent.run_agent_once


def main() -> None:
    run_agent_once = _ensure_import_run_agent()

    # 裸问一句：你是谁？
    response = run_agent_once(
        config_path=CONFIG_PATH,
        user_input="你是谁？",
        memory_policy=None,
        verbose=True,
    )

    print("\n=== 裸问结果 ===")
    print(response)


if __name__ == "__main__":
    main()
