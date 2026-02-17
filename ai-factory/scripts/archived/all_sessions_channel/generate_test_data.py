#!/usr/bin/env python3
"""
从 all_sessions.md 生成拥塞测试数据
提取大的对话段落
"""
import re

# 读取文档
with open('/root/ai-factory/documents/all_sessions.md', 'r', encoding='utf-8') as f:
    content = f.read()

# 提取对话段落 (USER -> ASSISTANT)
dialogues = []
current_dialogue = []

in_dialogue = False
for line in content.split('\n'):
    if '## 对话内容' in line:
        if current_dialogue and len(current_dialogue) > 200:  # 大于200行的段落
            dialogues.append('\n'.join(current_dialogue))
        current_dialogue = []
        in_dialogue = True
    elif in_dialogue:
        if line.startswith('---'):
            if current_dialogue and len(current_dialogue) > 200:
                dialogues.append('\n'.join(current_dialogue))
            current_dialogue = []
        else:
            current_dialogue.append(line)

# 按长度排序，取前10个最大的
dialogues.sort(key=len, reverse=True)

print(f"找到 {len(dialogues)} 个大段落")
print("\n最大的10个段落:")
for i, d in enumerate(dialogues[:10]):
    lines = d.count('\n') + 1
    chars = len(d)
    # 提取标题
    match = re.search(r'USER\n\*\*时间\*\*: (.+?)\n', d)
    time = match.group(1) if match else "Unknown"
    print(f"{i+1}. {lines} 行, {chars} 字符, 时间: {time}")

# 输出最大的5个用于测试
print("\n\n=== 用于测试的对话内容 ===")
for i, d in enumerate(dialogues[:5]):
    match = re.search(r'USER\n\*\*时间\*\*: (.+?)\n', d)
    time = match.group(1) if match else "Unknown"
    print(f"\n--- 对话 {i+1} (时间: {time}) ---")
    # 只输出ASSISTANT的内容（通常更长）
    assistant_match = re.search(r'ASSISTANT(.+?)(?=---|\Z)', d, re.DOTALL)
    if assistant_match:
        text = assistant_match.group(1).strip()
        # 清理markdown格式
        text = re.sub(r'\*\*.*?\*\*', '', text)
        text = re.sub(r'```[\s\S]*?```', '[代码块]', text)
        print(text[:3000])  # 输出前3000字符
