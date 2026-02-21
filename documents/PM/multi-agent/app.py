import os
import json
from flask import Flask, render_template, request, jsonify
from agent_a import create_agent_a
from md_writer import create_md_writer

app = Flask(__name__)

# 全局 Agent A 实例
agent_a = None


def get_agent_a():
    """获取或创建 Agent A 实例"""
    global agent_a
    if agent_a is None:
        opencode_url = os.getenv("OPENCODE_URL", "http://localhost:4096")
        md_file_path = os.getenv("MD_FILE_PATH", None)
        agent_a = create_agent_a(
            opencode_url=opencode_url,
            md_file_path=md_file_path
        )
    return agent_a


@app.route("/")
def index():
    """首页"""
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    """处理用户对话请求"""
    data = request.get_json()
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({
            "success": False,
            "error": "消息不能为空"
        })

    try:
        agent = get_agent_a()
        result = agent.execute(user_message)

        return jsonify({
            "success": True,
            "session_id": result.get("session_id", ""),
            "user_input": result["user_input"],
            "refined_input": result["refined_input"],
            "result": result["agent_b_result"],
            "duration": f"{result['duration_seconds']:.1f}秒",
            "timestamp": result["timestamp"]
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route("/api/history", methods=["GET"])
def history():
    """获取对话历史"""
    try:
        writer = create_md_writer()
        content = writer.get_recent_entries(count=10)
        return jsonify({
            "success": True,
            "content": content
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route("/api/health", methods=["GET"])
def health():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "agent_a": "ready" if agent_a else "not_initialized"
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"

    print(f"启动 Multi-Agent MVP 服务: http://localhost:{port}")
    print(f"OpenCode URL: {os.getenv('OPENCODE_URL', 'http://localhost:4096')}")
    print(f"请确保 OpenCode Server 已启动!")

    app.run(host="0.0.0.0", port=port, debug=debug)
