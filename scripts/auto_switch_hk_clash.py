#!/usr/bin/env python3
"""Clash 自动切换到香港节点的脚本。

用法:
    python auto_switch_hk_clash.py

环境变量依赖:
    - CLASH_HOST (默认: 127.0.0.1)
    - CLASH_PORT (默认: 9097)
    - CLASH_SECRET
"""

import os
import sys
import time
import requests
from typing import Optional


class ClashAutoSwitcher:
    """Clash 自动切换管理器"""

    def __init__(self):
        self.host = os.getenv("CLASH_HOST", "127.0.0.1")
        self.port = int(os.getenv("CLASH_PORT", "9097"))
        self.secret = os.getenv("CLASH_SECRET", "")
        self.base_url = f"http://{self.host}:{self.port}/configs"

    def _get_headers(self) -> dict:
        """获取 API 请求头"""
        return {
            "Authorization": f"Bearer {self.secret}",
            "Content-Type": "application/json"
        }

    def health_check(self) -> bool:
        """健康检查：Clash 是否可用"""
        try:
            resp = requests.get(
                f"{self.base_url}",
                headers=self._get_headers(),
                timeout=5
            )
            return resp.status_code == 200
        except Exception as e:
            print(f"[ERROR] Clash health check failed: {e}")
            return False

    def get_current_proxy(self) -> Optional[dict]:
        """获取当前选中的代理组"""
        try:
            resp = requests.get(
                f"{self.base_url}",
                headers=self._get_headers(),
                timeout=5
            )
            resp.raise_for_status()
            data = resp.json()

            # 查找 proxy-groups 中的当前选中
            for group in data.get("payload", {}).get("proxy-groups", []):
                if group.get("name", "").startswith("LanFanCloud"):
                    selected = group.get("now", "")
                    print(f"[INFO] Current proxy group: {group.get('name')}")
                    print(f"[INFO] Current selection: {selected}")

                    # 返回所有代理
                    proxies = group.get("proxies", [])
                    return {
                        "group_name": group.get("name"),
                        "current": selected,
                        "proxies": proxies
                    }

            print("[WARNING] LanFanCloud proxy group not found")
            return None

        except Exception as e:
            print(f"[ERROR] Failed to get current proxy: {e}")
            return None

    def switch_to_hk_proxy(self, timeout: int = 30) -> bool:
        """切换到香港节点

        Args:
            timeout: 最大等待时间（秒）

        Returns:
            bool: 是否成功切换
        """
        current = self.get_current_proxy()
        if not current:
            print("[ERROR] Cannot get current proxy status")
            return False

        proxies = current.get("proxies", [])
        print(f"[INFO] Available HK proxies: {proxies}")

        # 查找香港节点
        hk_proxies = [p for p in proxies if "香港" in p or "Hong Kong" in p.lower()]

        if not hk_proxies:
            print("[ERROR] No HK proxies found")
            return False

        # 优先选择第一个香港节点
        target_proxy = hk_proxies[0]
        print(f"[INFO] Target HK proxy: {target_proxy}")

        # 构造更新请求
        update_payload = {
            "payload": {
                "proxy-groups": [
                    {
                        "name": current["group_name"],
                        "type": "select",
                        "proxies": current["proxies"],
                        "now": target_proxy
                    }
                ]
            }
        }

        try:
            resp = requests.put(
                f"{self.base_url}",
                headers=self._get_headers(),
                json=update_payload,
                timeout=10
            )
            resp.raise_for_status()

            print(f"[SUCCESS] Switched to HK proxy: {target_proxy}")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to switch to HK proxy: {e}")
            return False


def main():
    """主函数"""
    print("=" * 60)
    print("Clash Auto Switcher - Hong Kong")
    print("=" * 60)

    # 健康检查
    print("\n[1/3] Checking Clash health...")
    switcher = ClashAutoSwitcher()

    if not switcher.health_check():
        print("[ERROR] Clash is not accessible. Please start Clash first.")
        sys.exit(1)

    print("[OK] Clash is healthy")

    # 获取当前代理
    print("\n[2/3] Getting current proxy status...")
    current = switcher.get_current_proxy()
    if not current:
        print("[ERROR] Failed to get current proxy")
        sys.exit(1)

    # 切换到香港节点
    print("\n[3/3] Switching to HK proxy...")
    success = switcher.switch_to_hk_proxy()

    if success:
        print("\n" + "=" * 60)
        print("[SUCCESS] Hong Kong proxy switched successfully!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("[FAILED] Failed to switch to HK proxy")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
