def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80):
    """把长文本切成带重叠的小片段，便于检索。"""
    cleaned = text.strip()
    if not cleaned:
        return []

    chunks = []
    start = 0

    while start < len(cleaned):
        end = start + chunk_size
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(cleaned):
            break

        start = max(end - overlap, start + 1)

    return chunks
