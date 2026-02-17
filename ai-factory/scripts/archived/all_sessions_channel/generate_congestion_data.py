#!/usr/bin/env python3
"""
从 all_sessions.md 生成真正的拥塞测试数据
提取最大的对话段落
"""
import re

# 读取文档
with open('/root/ai-factory/documents/all_sessions.md', 'r', encoding='utf-8') as f:
    content = f.read()

# 提取ASSISTANT的大段落
dialogues = []
current_dialogue = []
in_assistant = False

for line in content.split('\n'):
    if '### 🤖 ASSISTANT' in line:
        in_assistant = True
        current_dialogue = []
    elif in_assistant:
        if line.startswith('---'):
            if current_dialogue and len(current_dialogue) > 100:  # 大于100行的段落
                dialogues.append('\n'.join(current_dialogue))
            current_dialogue = []
            in_assistant = False
        elif line.startswith('### 👤 USER'):
            if current_dialogue and len(current_dialogue) > 100:
                dialogues.append('\n'.join(current_dialogue))
            current_dialogue = []
        else:
            current_dialogue.append(line)

# 按长度排序
dialogues.sort(key=len, reverse=True)

print(f"找到 {len(dialogues)} 个大段落")
print("\n最大的5个:")
for i, d in enumerate(dialogues[:5]):
    lines = d.count('\n') + 1
    chars = len(d)
    print(f"{i+1}. {lines} 行, {chars} 字符")

# 生成测试数据 - 取前20个大的对话
test_data = []
for i, d in enumerate(dialogues[:20]):
    # 清理markdown格式
    text = re.sub(r'\*\*.*?\*\*', '', d)  # 移除粗体
    text = re.sub(r'#+\s*', '', text)  # 移除标题标记
    text = re.sub(r'```[\s\S]*?```', '[代码块]', text)  # 简化代码块
    text = re.sub(r'\n+', '\n', text)  # 合并空行
    text = text.strip()
    
    if len(text) > 1000:  # 只保留大于1000字符的
        test_data.append({
            "index": i + 1,
            "chars": len(text),
            "content": text[:5000]  # 限制5000字符
        })

print(f"\n生成 {len(test_data)} 条测试数据")
print(f"总字符数: {sum(d['chars'] for d in test_data)}")

# 输出测试数据
import json
print("\n\n=== 测试数据 JSON ===")
for item in test_data[:5]:  # 输出前5条
    print(f"\n--- 测试 {item['index']} ({item['chars']} 字符) ---")
    print(item['content'][:1000] + "...")

# 保存到文件
with open('/root/ai-factory/test_congestion_data.json', 'w', encoding='utf-8') as f:
    json.dump(test_data, f, ensure_ascii=False, indent=2)

print(f"\n\n✅ 测试数据已保存到 /root/ai-factory/test_congestion_data.json")
