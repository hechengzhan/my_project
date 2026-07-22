from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

import json
import time

from graph.agent import app as agent_app

from memory.memory_store import add_memory, get_memory

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_ASSETS = FRONTEND_DIST / "assets"

app = FastAPI(title="Campus Agent Streaming API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.get("/")
def root():
    """返回前端首页；未打包前端时返回后端运行提示。"""
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return {"message": "Campus Agent Streaming Running"}


@app.get("/health")
@app.get("/api/health")
def health():
    """提供健康检查接口，用于确认后端服务是否正常。"""
    return {"status": "ok", "service": "campus-agent"}


@app.post("/api/chat")
@app.post("/chat")
def chat(req: ChatRequest):
    """普通聊天接口：调用智能体并一次性返回完整回答。"""
    state = {
        "input": req.message,
        "history": _build_history(req.session_id),
        "session_id": req.session_id,
    }
    result = agent_app.invoke(state)

    reply = result.get("result", "")
    add_memory(req.session_id, "user", req.message)
    add_memory(req.session_id, "assistant", reply)

    return {
        "reply": reply,
        "intent": result.get("intent"),
        "sources": result.get("sources", []),
    }


@app.post("/api/chat_stream")
@app.post("/chat_stream")
def chat_stream(req: ChatRequest):
    """流式聊天接口：调用智能体后按字符模拟 SSE 流式返回。"""
    user_input = req.message
    session_id = req.session_id

    add_memory(session_id, "user", user_input)

    state = {
        "input": user_input,
        "history": _build_history(session_id),
        "session_id": session_id,
    }

    result = agent_app.invoke(state)
    answer = result.get("result", "")
    intent = result.get("intent")
    sources = result.get("sources", [])

    add_memory(session_id, "assistant", answer)

    def generate():
        """逐字产出 SSE 数据，并在结尾发送元信息和完成标记。"""
        for char in answer:
            yield f"data: {json.dumps({'token': char}, ensure_ascii=False)}\n\n"
            time.sleep(0.02)

        yield f"data: {json.dumps({'intent': intent, 'sources': sources}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )


def _build_history(session_id: str) -> str:
    """按会话 ID 读取历史消息，并拼接成模型可用的文本。"""
    history = get_memory(session_id)
    return "\n".join(
        [f"{item['role']}: {item['content']}" for item in history]
    )


if FRONTEND_ASSETS.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_ASSETS),
        name="frontend-assets",
    )


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    """托管前端打包文件；找不到资源时回退到 index.html。"""
    requested_file = FRONTEND_DIST / full_path
    if requested_file.exists() and requested_file.is_file():
        return FileResponse(requested_file)

    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return {"message": "Frontend has not been built. Run npm.cmd run build in frontend first."}
