import hashlib
import os


_MODEL = None


def embed(text: str):
    """根据配置选择 hash 或语义模型，把文本转换为向量。"""
    provider = os.getenv("EMBEDDING_PROVIDER", "hash").strip().lower()

    if provider == "sentence_transformers":
        return _embed_with_sentence_transformers(text)

    return _hash_embed(text)


def _embed_with_sentence_transformers(text: str):
    """使用 sentence-transformers 模型生成语义向量。"""
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
        _MODEL = SentenceTransformer(model_name)

    return _MODEL.encode(text, normalize_embeddings=True).tolist()


def _hash_embed(text: str, dim: int = 128):
    """使用字符 hash 生成轻量向量，保证离线也能检索。"""
    vector = [0.0] * dim

    for index, char in enumerate(text):
        digest = hashlib.md5(f"{index}:{char}".encode("utf-8")).digest()
        bucket = digest[0] % dim
        vector[bucket] += 1.0

    norm = sum(value * value for value in vector) ** 0.5 or 1.0
    return [value / norm for value in vector]
