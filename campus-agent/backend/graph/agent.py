from langgraph.graph import StateGraph, END

from graph.state import AgentState

from graph.nodes.intent import intent_node
from graph.nodes.chat import chat_node
from graph.nodes.weather import weather_node
from graph.nodes.news import news_node
from graph.nodes.rag import rag_node


# ======================
# 构建图
# ======================
workflow = StateGraph(AgentState)

# 节点
workflow.add_node("intent", intent_node)
workflow.add_node("chat", chat_node)
workflow.add_node("weather", weather_node)
workflow.add_node("news", news_node)
workflow.add_node("rag", rag_node)


# 起点
workflow.set_entry_point("intent")


# ======================
# 路由逻辑（核心）
# ======================
def route(state):
    """根据意图识别结果决定下一个 LangGraph 节点。"""
    return state["intent"]


workflow.add_conditional_edges(
    "intent",
    route,
    {
        "chat": "chat",
        "weather": "weather",
        "news": "news",
        "rag": "rag"
    }
)

# 所有节点 → END
workflow.add_edge("chat", END)
workflow.add_edge("weather", END)
workflow.add_edge("news", END)
workflow.add_edge("rag", END)


# 编译
app = workflow.compile()
