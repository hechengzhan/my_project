from pathlib import Path

from rag.chunker import chunk_text
from rag.embedder import embed
from rag.loader import load_text_files
from rag.vector_store import add_vector, reset


PROJECT_ROOT = Path(__file__).resolve().parents[2]

KNOWLEDGE_DIRS = {
    "temp": PROJECT_ROOT / "knowledge" / "temp",
}


def build_index(source=None):
    """读取指定知识目录，完成切片、向量化并写入内存索引。"""
    sources = [source] if source else list(KNOWLEDGE_DIRS.keys())
    counts = {}

    for current_source in sources:
        directory = KNOWLEDGE_DIRS.get(current_source)
        if directory is None:
            counts[current_source] = 0
            continue

        reset(source=current_source)
        count = 0

        for file in load_text_files(directory):
            for chunk in chunk_text(file["text"]):
                add_vector(
                    text=chunk,
                    vector=embed(chunk),
                    metadata={"path": file["path"]},
                    source=current_source,
                )
                count += 1

        counts[current_source] = count

    return counts
