#!/usr/bin/env python3
"""
💾 entries_ingest CLI工具 - 标准化入库通道命令行接口

使用示例:
    # 直接入库（需要提供完整payload JSON）
    python entries_ingest_cli.py --payload '{"title":"测试","summary_ai":"摘要","raw_text":"内容","project_code":"pm-agent"}'
    
    # 从文件读取payload
    python entries_ingest_cli.py --file payload.json
    
    # 交互模式
    python entries_ingest_cli.py --interactive

返回:
    {"success": true, "entry_id": "ent_xxx", "title": "..."}
    {"success": false, "error": "..."}
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_factory.integrations.entries_ingest import entries_ingest


def cli():
    parser = argparse.ArgumentParser(
        description='💾 entries_ingest - 标准化入库通道',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
必填字段:
  - title: str (LLM生成的标题)
  - summary_ai: str (LLM生成的摘要)
  - raw_text: str (原始内容)
  - project_code: str (项目代码)

示例:
  python entries_ingest_cli.py --payload '{"title":"架构设计","summary_ai":"完成了...","raw_text":"详细内容","project_code":"pm-agent"}'
        '''
    )
    
    parser.add_argument(
        '--payload', '-p',
        type=str,
        help='JSON格式的payload字符串'
    )
    
    parser.add_argument(
        '--file', '-f',
        type=str,
        help='包含payload的JSON文件路径'
    )
    
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='交互式输入（逐步提示输入字段）'
    )
    
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='模拟运行，验证payload但不实际入库'
    )
    
    args = parser.parse_args()
    
    # 获取payload
    payload = None
    
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception as e:
            print(json.dumps({"success": False, "error": f"读取文件失败: {e}"}, ensure_ascii=False))
            sys.exit(1)
    
    elif args.payload:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as e:
            print(json.dumps({"success": False, "error": f"JSON解析失败: {e}"}, ensure_ascii=False))
            sys.exit(1)
    
    elif args.interactive:
        print("💾 entries_ingest 交互式输入")
        print("-" * 50)
        payload = {}
        payload['title'] = input("标题 (title): ").strip()
        payload['summary_ai'] = input("摘要 (summary_ai): ").strip()
        payload['raw_text'] = input("原始内容 (raw_text): ").strip()
        payload['project_code'] = input("项目代码 (project_code): ").strip()
        user_id = input("用户ID (user_id, 默认pm-agent): ").strip()
        if user_id:
            payload['user_id'] = user_id
        print("-" * 50)
    
    else:
        parser.print_help()
        sys.exit(1)
    
    # 验证必填字段
    required = ['title', 'summary_ai', 'raw_text', 'project_code']
    missing = [f for f in required if not payload.get(f)]
    if missing:
        print(json.dumps({
            "success": False,
            "error": f"必填字段缺失: {missing}",
            "required": required,
            "provided": list(payload.keys())
        }, ensure_ascii=False))
        sys.exit(1)
    
    # 模拟运行
    if args.dry_run:
        print(json.dumps({
            "success": True,
            "dry_run": True,
            "payload": payload,
            "message": "✅ payload验证通过（模拟模式，未实际入库）"
        }, ensure_ascii=False, indent=2))
        sys.exit(0)
    
    # 执行入库
    try:
        result = entries_ingest(payload)
        entry_id = result.get("entries", [{}])[0].get("entry_id", "unknown")
        title = result.get("entries", [{}])[0].get("title", "")
        
        output = {
            "success": True,
            "entry_id": entry_id,
            "title": title,
            "project_code": payload.get("project_code"),
            "message": f"✅ 入库成功: {entry_id}"
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(json.dumps({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    cli()
