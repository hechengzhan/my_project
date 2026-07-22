from llm.client import call_general_llm
from llm.prompt import build_chat_prompt


def chat_node(state):
    """普通聊天节点：构造提示词并调用通用大模型回答。"""
    prompt = build_chat_prompt(
        question=state["input"],
        history=state.get("history", ""),
    )

    return {
        "result": call_general_llm(prompt, session_id=state.get("session_id")),
        "sources": ["general_llm"],
    }
