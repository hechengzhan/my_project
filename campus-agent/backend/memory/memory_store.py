from collections import defaultdict

# =========================
# 🧠 简易内存（按 session 存）
# =========================
MEMORY = defaultdict(list)

MAX_HISTORY = 10


def add_memory(session_id: str, role: str, content: str):
    """向指定会话追加一条消息，并只保留最近的历史记录。"""
    MEMORY[session_id].append({
        "role": role,
        "content": content
    })

    # 控制长度
    if len(MEMORY[session_id]) > MAX_HISTORY:
        MEMORY[session_id] = MEMORY[session_id][-MAX_HISTORY:]


def get_memory(session_id: str):
    """读取指定会话的历史消息列表。"""
    return MEMORY[session_id]
