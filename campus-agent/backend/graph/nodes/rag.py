from llm.client import call_general_llm, call_llm
from llm.prompt import (
    build_campus_fallback_prompt,
    build_combined_answer_prompt,
)
from rag.build_index import build_index
from rag.retriever import retrieve


def rag_node(state):
    """校园问答节点：检索本地通知并结合 Coze 知识库生成回答。"""
    query = state["input"]
    history = state.get("history", "")

    build_index(source="temp")
    docs = retrieve(query, source="temp", top_k=5)
    temp_context = "\n\n".join(doc["text"] for doc in docs)

    coze_answer = call_llm(query)

    if not docs:
        if _should_fallback_to_chat(coze_answer):
            fallback = _try_chat_fallback(
                state,
                reason="校园资料和 Coze 知识库没有找到相关信息",
            )
            if fallback:
                return fallback

        return {
            "result": coze_answer,
            "sources": ["coze_knowledge_base"],
        }

    prompt = build_combined_answer_prompt(
        question=query,
        coze_answer=coze_answer,
        temp_context=temp_context,
        history=history,
    )

    result = _clean_source_prefix(call_llm(prompt))

    if _should_fallback_to_chat(result):
        fallback = _try_chat_fallback(
            state,
            reason="Coze 知识库和本地最新通知没有形成可直接引用的准确答案",
        )
        if fallback:
            return fallback

        result = _extract_relevant_temp_answer(query, temp_context)

    return {
        "result": result,
        "sources": ["coze_knowledge_base"] + [
            doc.get("metadata", {}).get("path", "knowledge/temp")
            for doc in docs
        ],
    }


def _clean_source_prefix(answer: str) -> str:
    """去掉模型回答开头生硬的来源前缀。"""
    cleaned = answer.strip()
    prefixes = [
        "根据本地最新通知资料，",
        "根据本地最新通知，",
        "根据最新通知资料，",
        "根据最新通知，",
        "根据本地最新通知资料：",
        "根据本地最新通知：",
        "根据最新通知资料：",
        "根据最新通知：",
    ]

    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].lstrip()
                changed = True

    return cleaned


def _should_fallback_to_chat(answer: str) -> bool:
    """判断 Coze 或综合回答是否无效，是否需要兜底。"""
    if not answer:
        return True

    fallback_markers = [
        "资料中没有找到相关信息",
        "资料里没有找到",
        "没有找到相关信息",
        "知识库没有返回明确答案",
        "Coze API 调用失败",
        "当前无法连接真实模型",
    ]
    return any(marker in answer for marker in fallback_markers)


def _extract_relevant_temp_answer(query: str, temp_context: str) -> str:
    """模型兜底失败时，从本地通知中抽取最相关句子。"""
    query_features = _features(query)
    candidates = [
        line.strip()
        for line in temp_context.replace("。", "。\n").splitlines()
        if line.strip()
    ]

    scored = []
    for line in candidates:
        line_features = _features(line)
        score = len(query_features & line_features)
        for token in query_features:
            if len(token) >= 2 and token in line:
                score += 2
        if score > 0:
            scored.append((score, line))

    if not scored:
        return temp_context.strip()

    scored.sort(key=lambda item: item[0], reverse=True)
    return _clean_source_prefix(scored[0][1])


def _features(text: str):
    """提取文本连续字符特征，用于本地句子相关性评分。"""
    compact = "".join(char for char in text.lower().strip() if not char.isspace())
    features = set()
    for size in (2, 3, 4):
        for index in range(0, max(len(compact) - size + 1, 0)):
            features.add(compact[index:index + size])
    return features


def _try_chat_fallback(state, reason: str):
    """调用 DeepSeek 生成校园问答兜底回答。"""
    prompt = build_campus_fallback_prompt(
        question=state["input"],
        reason=reason,
        history=state.get("history", ""),
    )

    answer = call_general_llm(prompt, session_id=state.get("session_id"))
    if _deepseek_fallback_failed(answer):
        return None

    return {
        "result": answer,
        "sources": ["deepseek_fallback"],
    }


def _deepseek_fallback_failed(answer: str) -> bool:
    """判断 DeepSeek 兜底是否也调用失败。"""
    failed_markers = [
        "DeepSeek API 调用失败",
        "当前无法连接 DeepSeek 模型服务",
        "请先配置 DEEPSEEK",
    ]
    return any(marker in answer for marker in failed_markers)
