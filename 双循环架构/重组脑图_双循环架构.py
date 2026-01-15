#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脑图重组脚本 - 基于双循环架构语义重组
将原始脑图文件按照双循环架构重新组织，生成符合jsmind v2.1规范的新JSON文档

功能特点：
1. 基于语义分析进行节点分类
2. 支持双循环架构（大循环+小循环）
3. 完全去重处理
4. 保留所有时间戳
5. 符合jsmind v2.1扁平格式规范
6. 支持最大10级嵌套
"""

import json
import os
import re
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Set
import hashlib

class MindmapReorganizer:
    """脑图重组器 - 基于双循环架构"""
    
    def __init__(self):
        self.node_counter = 0
        self.duplicate_nodes = set()
        self.semantic_categories = {
            # 大循环节点（战略层）
            "战略目标": ["战略", "愿景", "目标", "方向", "规划", "蓝图"],
            "业务规划": ["业务", "产品", "市场", "运营", "商业模式"],
            "技术架构": ["架构", "设计", "框架", "系统", "平台", "技术栈"],
            "资源规划": ["资源", "人力", "预算", "时间", "设备", "基础设施"],
            
            # 小循环节点（执行层）
            "项目任务": ["项目", "任务", "工作", "实施", "执行", "完成"],
            "工作议题": ["议题", "问题", "讨论", "决策", "分析", "评估"],
            "学习笔记": ["笔记", "学习", "总结", "记录", "文档", "知识"],
            "技术实现": ["实现", "代码", "开发", "编程", "调试", "测试"]
        }
        
        # 保持结构的父子关系关键词
        self.preserved_relationships = [
            "标签管理", "重要文档", "计划", "规划", "工作流", "项目",
            "任务", "议题", "笔记", "记录", "文档", "文件"
        ]
    
    def generate_node_id(self, prefix: str = "node") -> str:
        """生成唯一节点ID"""
        self.node_counter += 1
        return f"{prefix}_{self.node_counter:06d}"
    
    def get_semantic_category(self, topic: str, content: str = "") -> str:
        """基于语义分析确定节点类别"""
        text = (topic + " " + content).lower()
        
        # 检查是否应该保持原有结构
        for keyword in self.preserved_relationships:
            if keyword in topic:
                return "保持结构"
        
        # 语义分类
        for category, keywords in self.semantic_categories.items():
            for keyword in keywords:
                if keyword in text:
                    return category
        
        return "其他"
    
    def calculate_content_hash(self, topic: str, content: str = "") -> str:
        """计算内容哈希值用于去重"""
        content_str = topic + "|" + content
        return hashlib.md5(content_str.encode('utf-8')).hexdigest()
    
    def extract_timestamp(self, node: Dict) -> Optional[int]:
        """从节点中提取时间戳"""
        # 尝试从各种字段中提取时间戳
        timestamp_fields = ['createdAt', 'updatedAt', 'timestamp', 'create_time', 'update_time']
        
        for field in timestamp_fields:
            if field in node and node[field]:
                timestamp = node[field]
                if isinstance(timestamp, (int, float)) and timestamp > 0:
                    return int(timestamp)
        
        # 如果没有时间戳，使用当前时间
        return int(datetime.now().timestamp() * 1000)
    
    def normalize_node_format(self, node: Dict, parent_id: str = None) -> Dict:
        """将节点转换为jsmind v2.1规范格式"""
        normalized = {
            "id": node.get("id", self.generate_node_id()),
            "topic": node.get("topic", "").strip(),
            "expanded": node.get("expanded", True)
        }
        
        # 添加内容字段
        if "content" in node and node["content"]:
            normalized["content"] = node["content"]
        
        # 添加时间戳
        timestamp = self.extract_timestamp(node)
        if timestamp:
            normalized["createdAt"] = timestamp
            normalized["updatedAt"] = timestamp
        
        # 添加父节点关系
        if parent_id:
            normalized["parentid"] = parent_id
        
        # 保留其他重要字段
        important_fields = ["tags", "status", "priority", "assignee", "itemType"]
        for field in important_fields:
            if field in node and node[field]:
                normalized[field] = node[field]
        
        return normalized
    
    def process_node_recursive(self, node: Dict, parent_id: str = None, level: int = 0, 
                             content_hashes: Set = None, processed_nodes: List = None) -> List[Dict]:
        """递归处理节点树"""
        if content_hashes is None:
            content_hashes = set()
        if processed_nodes is None:
            processed_nodes = []
        
        # 检查嵌套深度
        if level > 10:
            print(f"警告: 节点 {node.get('topic', '未知')} 超过最大嵌套深度10级")
            return processed_nodes
        
        # 计算内容哈希并检查重复
        topic = node.get("topic", "").strip()
        content = node.get("content", "")
        content_hash = self.calculate_content_hash(topic, content)
        
        if content_hash in content_hashes:
            self.duplicate_nodes.add(topic)
            return processed_nodes
        
        content_hashes.add(content_hash)
        
        # 规范化当前节点
        normalized_node = self.normalize_node_format(node, parent_id)
        
        # 语义分类
        category = self.get_semantic_category(topic, content)
        if category != "保持结构":
            normalized_node["category"] = category
        
        processed_nodes.append(normalized_node)
        current_node_id = normalized_node["id"]
        
        # 递归处理子节点
        children = node.get("children", [])
        for child in children:
            self.process_node_recursive(child, current_node_id, level + 1, content_hashes, processed_nodes)
        
        return processed_nodes
    
    def build_dual_cycle_structure(self, flat_nodes: List[Dict]) -> Dict:
        """构建双循环架构的脑图结构"""
        
        # 按语义类别分组
        categorized_nodes = {}
        for node in flat_nodes:
            category = node.get("category", "其他")
            if category not in categorized_nodes:
                categorized_nodes[category] = []
            categorized_nodes[category].append(node)
        
        # 创建根节点（独立议题）
        root_nodes = []
        
        # 大循环根节点
        big_cycle_categories = ["战略目标", "业务规划", "技术架构", "资源规划"]
        for category in big_cycle_categories:
            if category in categorized_nodes and categorized_nodes[category]:
                root_node = {
                    "id": self.generate_node_id("big_cycle"),
                    "topic": category,
                    "expanded": True,
                    "children": categorized_nodes[category],
                    "category": "大循环"
                }
                root_nodes.append(root_node)
        
        # 小循环根节点
        small_cycle_categories = ["项目任务", "工作议题", "学习笔记", "技术实现"]
        for category in small_cycle_categories:
            if category in categorized_nodes and categorized_nodes[category]:
                root_node = {
                    "id": self.generate_node_id("small_cycle"),
                    "topic": category,
                    "expanded": True,
                    "children": categorized_nodes[category],
                    "category": "小循环"
                }
                root_nodes.append(root_node)
        
        # 其他节点
        if "其他" in categorized_nodes and categorized_nodes["其他"]:
            other_node = {
                "id": self.generate_node_id("other"),
                "topic": "其他",
                "expanded": True,
                "children": categorized_nodes["其他"],
                "category": "其他"
            }
            root_nodes.append(other_node)
        
        # 保持结构的节点（直接作为根节点）
        if "保持结构" in categorized_nodes and categorized_nodes["保持结构"]:
            for node in categorized_nodes["保持结构"]:
                root_nodes.append(node)
        
        return root_nodes
    
    def reorganize_mindmap(self, input_file: str, output_file: str) -> Dict:
        """主重组函数"""
        print(f"开始处理脑图文件: {input_file}")
        
        try:
            # 读取原始文件
            with open(input_file, 'r', encoding='utf-8') as f:
                original_data = json.load(f)
        except Exception as e:
            print(f"读取文件失败: {e}")
            return None
        
        print(f"原始文件读取成功，开始分析节点结构...")
        
        # 重置计数器
        self.node_counter = 0
        self.duplicate_nodes.clear()
        
        # 提取所有节点并扁平化处理
        flat_nodes = []
        
        # 处理根节点
        if "data" in original_data:
            # jsmind格式
            root_node = original_data["data"]
            flat_nodes = self.process_node_recursive(root_node)
        elif isinstance(original_data, list):
            # 节点数组格式
            for node in original_data:
                flat_nodes.extend(self.process_node_recursive(node))
        elif "children" in original_data:
            # 嵌套格式
            flat_nodes = self.process_node_recursive(original_data)
        else:
            print("无法识别的脑图格式")
            return None
        
        print(f"节点处理完成: 共处理 {len(flat_nodes)} 个节点")
        print(f"去重处理: 移除 {len(self.duplicate_nodes)} 个重复节点")
        
        # 构建双循环架构
        reorganized_structure = self.build_dual_cycle_structure(flat_nodes)
        
        # 创建符合jsmind v2.1规范的输出
        output_data = {
            "meta": {
                "name": "重组脑图 - 双循环架构",
                "author": "脑图重组脚本",
                "version": "2.1",
                "createdAt": int(datetime.now().timestamp() * 1000),
                "sourceFile": os.path.basename(input_file),
                "reorganizationTime": datetime.now().isoformat(),
                "statistics": {
                    "totalNodes": len(flat_nodes),
                    "duplicateNodesRemoved": len(self.duplicate_nodes),
                    "rootNodes": len(reorganized_structure),
                    "categories": list(set([node.get("category", "未知") for node in flat_nodes]))
                }
            },
            "format": "node_tree",
            "data": {
                "id": "root_dual_cycle",
                "topic": "双循环架构脑图",
                "expanded": True,
                "children": reorganized_structure
            }
        }
        
        # 保存输出文件
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            print(f"重组完成！输出文件: {output_file}")
        except Exception as e:
            print(f"保存文件失败: {e}")
            return None
        
        return output_data

def main():
    """主函数"""
    # 输入文件路径
    input_file = r"D:\AI\项目文件外存处\拼接脑图 - 副本.json"
    
    # 输出文件路径（与输入文件相同目录）
    output_dir = os.path.dirname(input_file)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"重组脑图_双循环架构_{timestamp}.json"
    output_file = os.path.join(output_dir, output_filename)
    
    # 创建重组器实例
    reorganizer = MindmapReorganizer()
    
    # 执行重组
    result = reorganizer.reorganize_mindmap(input_file, output_file)
    
    if result:
        print("\n=== 重组完成报告 ===")
        stats = result["meta"]["statistics"]
        print(f"总节点数: {stats['totalNodes']}")
        print(f"去重节点数: {stats['duplicateNodesRemoved']}")
        print(f"根节点数: {stats['rootNodes']}")
        print(f"分类类别: {', '.join(stats['categories'])}")
        print(f"输出文件: {output_file}")
        
        # 显示重复节点（如果有）
        if reorganizer.duplicate_nodes:
            print(f"\n重复节点列表:")
            for node in list(reorganizer.duplicate_nodes)[:10]:  # 只显示前10个
                print(f"  - {node}")
            if len(reorganizer.duplicate_nodes) > 10:
                print(f"  ... 还有 {len(reorganizer.duplicate_nodes) - 10} 个重复节点")
    else:
        print("重组失败！")

if __name__ == "__main__":
    main()