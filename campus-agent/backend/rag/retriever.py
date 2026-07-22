from rag.embedder import embed
from rag.vector_store import get_items, has_items, search


def retrieve(query: str, source=None, top_k: int = 3):
    """检索与用户问题最相关的文本片段，优先词面匹配。"""
    lexical_results = _lexical_search(query, source=source, top_k=top_k)
    if lexical_results:
        return lexical_results

    if source == "temp":
        return []

    if not has_items(source):
        return []

    return search(embed(query), source=source, top_k=top_k)


def _lexical_search(query: str, source=None, top_k: int = 3):
    """通过词和连续字符片段重合度进行轻量文本检索。"""
    query_features = _features(query)
    if not query_features:
        return []

    scored = []
    for item in get_items(source):
        text = item["text"]
        text_features = _features(text)
        overlap = query_features & text_features
        score = len(overlap)

        # Reward exact useful substrings heavily for short campus notices.
        for token in query_features:
            if len(token) >= 2 and token in text:
                score += 2

        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "text": item["text"],
            "metadata": item["metadata"],
            "source": item["source"],
            "score": score,
        }
        for score, item in scored[:top_k]
    ]


def _features(text: str):
    """提取文本的词面特征，用于计算检索重合度。"""
    cleaned = text.lower().strip()
    if not cleaned:
        return set()

    features = set()
    for part in cleaned.replace("，", " ").replace("。", " ").replace("？", " ").split():
        if part:
            features.add(part)

    compact = "".join(char for char in cleaned if not char.isspace())
    for size in (2, 3, 4):
        for index in range(0, max(len(compact) - size + 1, 0)):
            features.add(compact[index:index + size])

    return features
