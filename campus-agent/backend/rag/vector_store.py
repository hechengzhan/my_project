from math import sqrt


_ITEMS = []


def reset(source=None):
    """清空全部索引，或只清空指定来源的索引数据。"""
    global _ITEMS
    if source is None:
        _ITEMS = []
        return

    _ITEMS = [item for item in _ITEMS if item.get("source") != source]


def add_vector(text, vector, metadata=None, source="temp"):
    """向内存向量库添加一个文本片段及其向量。"""
    _ITEMS.append({
        "text": text,
        "vector": vector,
        "metadata": metadata or {},
        "source": source,
    })


def has_items(source=None):
    """判断内存向量库中是否存在指定来源的数据。"""
    if source is None:
        return bool(_ITEMS)
    return any(item.get("source") == source for item in _ITEMS)


def get_items(source=None):
    """读取全部索引项，或读取指定来源的索引项。"""
    if source is None:
        return list(_ITEMS)
    return [item for item in _ITEMS if item.get("source") == source]


def search(query_vector, source=None, top_k=3):
    """按余弦相似度搜索最相关的文本片段。"""
    candidates = get_items(source)
    scored = []

    for item in candidates:
        score = _cosine(query_vector, item["vector"])
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


def _cosine(left, right):
    """计算两个向量之间的余弦相似度。"""
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = sqrt(sum(a * a for a in left)) or 1.0
    right_norm = sqrt(sum(b * b for b in right)) or 1.0
    return numerator / (left_norm * right_norm)
