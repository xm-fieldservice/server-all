"""
2号通道测试脚本

测试异步任务管理功能：
1. 提交NOTE任务
2. 提交RAG任务
3. 提交WEB任务
4. 查询任务状态
5. 列出所有任务
"""

import time
import requests
import json

API_BASE = "http://localhost:8001"


def test_note_task():
    """测试NOTE任务（笔记入库）"""
    print("\n" + "=" * 60)
    print("测试1: 提交NOTE任务（笔记入库）")
    print("=" * 60)

    note_payload = {
        "task_type": "note",
        "payload": {
            "raw_text": "今天完成了双通道设计，1号通道同步写库，2号通道异步整理+RAG+Web。",
            "note_datetime": "2026-01-29 10:00:00",
        }
    }

    response = requests.post(f"{API_BASE}/ai-factory/tasks/ingest", json=note_payload)
    print(f"响应状态码: {response.status_code}")
    print(f"响应内容: {response.text}")

    result = response.json()
    if result.get("ok"):
        job_id = result.get("job_id")
        print(f"\n任务已提交: {job_id}")
        return job_id, note_payload
    else:
        print(f"\n提交失败: {result}")
        return None, None


def test_rag_task(job_id: str = None):
    """测试RAG任务"""
    print("\n" + "=" * 60)
    print("测试2: 提交RAG查询任务")
    print("=" * 60)

    rag_payload = {
        "task_type": "rag",
        "payload": {
            "question_text": "双通道设计的特点是什么？",
        }
    }

    response = requests.post(f"{API_BASE}/ai-factory/tasks/ingest", json=rag_payload)
    print(f"响应状态码: {response.status_code}")
    print(f"响应内容: {response.text}")

    result = response.json()
    if result.get("ok"):
        job_id = result.get("job_id")
        print(f"\n任务已提交: {job_id}")
        return job_id, rag_payload
    else:
        print(f"\n提交失败: {result}")
        return None, None


def test_web_task(job_id: str = None):
    """测试WEB任务"""
    print("\n" + "=" * 60)
    print("测试3: 提交Web查询任务")
    print("=" * 60)

    web_payload = {
        "task_type": "web",
        "payload": {
            "question_text": "什么是AI双通道架构？",
        }
    }

    response = requests.post(f"{API_BASE}/ai-factory/tasks/ingest", json=web_payload)
    print(f"响应状态码: {response.status_code}")
    print(f"响应内容: {response.text}")

    result = response.json()
    if result.get("ok"):
        job_id = result.get("job_id")
        print(f"\n任务已提交: {job_id}")
        return job_id, web_payload
    else:
        print(f"\n提交失败: {result}")
        return None, None


def wait_for_task_completion(job_id: str, timeout: int = 60):
    """等待任务完成"""
    print(f"\n等待任务完成: {job_id}")

    start_time = time.time()
    while time.time() - start_time < timeout:
        response = requests.get(f"{API_BASE}/ai-factory/tasks/ingest/{job_id}")
        result = response.json()

        if result.get("ok"):
            status = result.get("status")
            print(f"状态: {status}", end="\r")

            if status == "succeeded":
                print(f"\n任务成功完成！")
                return result
            elif status == "failed":
                print(f"\n任务失败!")
                print(f"错误码: {result.get('error_code')}")
                print(f"错误信息: {result.get('error_message')}")
                return None

        time.sleep(2)

    print(f"\n任务超时！")
    return None


def list_all_tasks():
    """列出所有任务"""
    print("\n" + "=" * 60)
    print("列出所有任务")
    print("=" * 60)

    response = requests.get(f"{API_BASE}/ai-factory/tasks", params={"limit": 20})
    result = response.json()

    if result.get("ok"):
        tasks = result.get("tasks", [])
        print(f"\n总任务数: {result.get('count')}")
        print(f"\n任务列表:")
        for task in tasks:
            print(f"  - {task['job_id']}: {task['task_type']} - {task['status']} - {task.get('entry_id')}")
    else:
        print(f"查询失败: {result}")


def main():
    """主函数"""
    print("2号通道测试脚本")
    print("=" * 60)

    # 测试1: 提交NOTE任务
    note_job_id, note_payload = test_note_task()

    # 测试2: 提交RAG任务
    rag_job_id, rag_payload = test_rag_task()

    # 测试3: 提交WEB任务
    web_job_id, web_payload = test_web_task()

    # 保存payload供后续使用
    if note_job_id:
        _current_note_payload = note_payload
    if rag_job_id:
        _current_rag_payload = rag_payload
    if web_job_id:
        _current_web_payload = web_payload

    # 等待任务完成
    if note_job_id:
        wait_for_task_completion(note_job_id)

    if rag_job_id:
        wait_for_task_completion(rag_job_id, timeout=120)  # RAG可能更慢

    if web_job_id:
        wait_for_task_completion(web_job_id, timeout=120)  # Web可能更慢

    # 列出所有任务
    list_all_tasks()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
