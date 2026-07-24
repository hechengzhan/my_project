"""校园助手的本地 RAG 知识库与大模型调用逻辑。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import chromadb
from openai import OpenAI
from pypdf import PdfReader


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
CHROMA_DIR = DATA_DIR / "chroma"
MANIFEST_PATH = DATA_DIR / "index_manifest.json"
UPLOAD_DIR = APP_DIR / "uploads"
COLLECTION_NAME = "campus_regulations"

EMBEDDING_MODEL = "text-embedding-v4"
EMBEDDING_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

CHUNK_SIZE = 450
CHUNK_OVERLAP = 50
TOP_K = 3
# Chroma 的 cosine distance 越小越相关；较高于此值时，拒绝让模型作答。
MAX_RETRIEVAL_DISTANCE = 0.48
ARTICLE_PATTERN = re.compile(r"第\s*[一二三四五六七八九十百千万零〇0-9]+\s*条")


class RagError(RuntimeError):
    """面向界面展示的 RAG 运行错误。"""


@dataclass(frozen=True)
class SourceChunk:
    """一次检索中可追溯的原始片段。"""

    text: str
    source_name: str
    page: int
    article: str
    distance: float

    @property
    def citation(self) -> str:
        article_text = self.article if self.article else "未标注条款"
        excerpt = re.sub(r"\s+", " ", self.text).strip()
        if len(excerpt) > 150:
            excerpt = f"{excerpt[:150]}…"
        return f"依据：《{self.source_name}》第 {self.page} 页 {article_text}：{excerpt}"


def _normalise_text(text: str) -> str:
    """保留段落边界，并消除 PDF 提取时产生的多余空白。"""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _article_for_chunk(text: str, start: int, end: int, fallback: str) -> str:
    """取切片所属的真实条款号，避免回答时臆造条款。"""
    previous_matches = list(ARTICLE_PATTERN.finditer(text[:start]))
    if previous_matches:
        return previous_matches[-1].group(0).replace(" ", "")
    # 当前片段从章节标题或前言开始时，条款名可能位于片段中间。
    in_chunk_match = ARTICLE_PATTERN.search(text[start:end])
    if in_chunk_match:
        return in_chunk_match.group(0).replace(" ", "")
    return fallback


def split_text(text: str, initial_article: str = "") -> list[tuple[str, str]]:
    """按约 450 字符切分，并优先在自然语义边界断开。"""
    clean_text = _normalise_text(text)
    chunks: list[tuple[str, str]] = []
    start = 0
    length = len(clean_text)

    while start < length:
        end = min(start + CHUNK_SIZE, length)
        if end < length:
            boundary = max(
                clean_text.rfind("\n", start + int(CHUNK_SIZE * 0.55), end),
                clean_text.rfind("。", start + int(CHUNK_SIZE * 0.55), end),
                clean_text.rfind("；", start + int(CHUNK_SIZE * 0.55), end),
            )
            if boundary > start:
                end = boundary + 1

        chunk = clean_text[start:end].strip()
        if chunk:
            chunks.append((chunk, _article_for_chunk(clean_text, start, end, initial_article)))
        if end >= length:
            break
        start = max(end - CHUNK_OVERLAP, start + 1)

    return chunks


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_document_id(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"documents": {}}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"documents": {}}


def _save_manifest(manifest: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def find_student_handbook() -> Path | None:
    """寻找项目根目录中默认的学生手册 PDF。"""
    pdfs = sorted(APP_DIR.glob("*.pdf"))
    if not pdfs:
        return None
    return next((path for path in pdfs if "学生手册" in path.name), pdfs[0])


def dashscope_base_url(workspace_id: str = "") -> str:
    """有业务空间 ID 时使用百炼推荐的专属域名，否则使用兼容地址。"""
    workspace_id = workspace_id.strip()
    if workspace_id:
        return f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    return EMBEDDING_BASE_URL


class KnowledgeBase:
    """使用 ChromaDB 持久化管理学校规章制度。"""

    def __init__(self, dashscope_api_key: str, workspace_id: str = "") -> None:
        if not dashscope_api_key.strip():
            raise RagError("请先在侧边栏填写 DashScope Embedding API Key。")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.embedding_client = OpenAI(
            api_key=dashscope_api_key.strip(), base_url=dashscope_base_url(workspace_id)
        )
        self.chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self.embedding_client.embeddings.create(
                model=EMBEDDING_MODEL, input=texts
            )
        except Exception as exc:  # API 的具体异常随 SDK 版本变化
            raise RagError(f"DashScope Embedding 调用失败：{exc}") from exc
        return [item.embedding for item in response.data]

    def document_count(self) -> int:
        return self.collection.count()

    def save_uploaded_pdf(self, filename: str, file_bytes: bytes) -> Path:
        """以内容哈希保存上传文件，重复上传不会产生重复副本。"""
        safe_name = re.sub(r"[^\w.\-()（）\u4e00-\u9fff]", "_", Path(filename).name)
        digest = hashlib.sha256(file_bytes).hexdigest()[:12]
        target = UPLOAD_DIR / f"{digest}_{safe_name}"
        if not target.exists():
            target.write_bytes(file_bytes)
        return target

    def index_document(self, path: Path, display_name: str | None = None) -> str:
        """变更过的 PDF 才会重新向量化，索引写入本地磁盘。"""
        if not path.exists():
            raise RagError(f"找不到 PDF：{path.name}")

        document_id = _safe_document_id(path)
        checksum = _file_hash(path)
        manifest = _load_manifest()
        old_record = manifest["documents"].get(document_id)
        if old_record and old_record.get("sha256") == checksum:
            return f"《{display_name or path.stem}》已在本地知识库中，无需重复构建。"

        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            raise RagError(f"无法读取《{path.name}》，请确认它是未加密、可解析的 PDF。") from exc

        records: list[tuple[str, dict[str, Any], str]] = []
        previous_article = ""
        for page_number, page in enumerate(reader.pages, start=1):
            raw_text = page.extract_text() or ""
            if not raw_text.strip():
                continue
            page_articles = list(ARTICLE_PATTERN.finditer(raw_text))
            for chunk_index, (chunk, article) in enumerate(
                split_text(raw_text, previous_article)
            ):
                records.append(
                    (
                        chunk,
                        {
                            "document_id": document_id,
                            "source_name": display_name or path.stem,
                            "page": page_number,
                            "article": article or "未标注条款",
                            "chunk_index": chunk_index,
                        },
                        f"{document_id}-{page_number}-{chunk_index}",
                    )
                )
            if page_articles:
                previous_article = page_articles[-1].group(0).replace(" ", "")

        if not records:
            raise RagError(f"《{path.name}》未提取到可检索文字，可能是扫描版 PDF。")

        # 文件更新或上一次构建中断时，先清理旧切片，确保检索结果没有过期或重复内容。
        self.collection.delete(where={"document_id": document_id})

        # DashScope text-embedding-v4 的单次 input 上限为 10 条文本。
        batch_size = 10
        for offset in range(0, len(records), batch_size):
            batch = records[offset : offset + batch_size]
            texts = [item[0] for item in batch]
            embeddings = self._embed(texts)
            self.collection.add(
                ids=[item[2] for item in batch],
                documents=texts,
                metadatas=[item[1] for item in batch],
                embeddings=embeddings,
            )

        manifest["documents"][document_id] = {
            "sha256": checksum,
            "source_name": display_name or path.stem,
            "path": str(path),
            "embedding_model": EMBEDDING_MODEL,
        }
        _save_manifest(manifest)
        return f"《{display_name or path.stem}》已完成索引，共写入 {len(records)} 个文本块。"

    def search(self, question: str, top_k: int = TOP_K) -> list[SourceChunk]:
        document_count = self.document_count()
        if document_count == 0:
            raise RagError("知识库还是空的，请先构建学生手册索引。")
        question_embedding = self._embed([question])[0]
        try:
            result = self.collection.query(
                query_embeddings=[question_embedding],
                n_results=min(top_k, document_count),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise RagError(f"知识库检索失败：{exc}") from exc

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            SourceChunk(
                text=document,
                source_name=str(metadata["source_name"]),
                page=int(metadata["page"]),
                article=str(metadata.get("article", "未标注条款")),
                distance=float(distance),
            )
            for document, metadata, distance in zip(documents, metadatas, distances)
        ]


def answer_question(
    question: str,
    deepseek_api_key: str,
    knowledge_base: KnowledgeBase,
    history: Iterable[dict[str, str]],
) -> tuple[str, list[SourceChunk], bool]:
    """严格依据 Top-3 片段作答；证据不足时直接拒答。"""
    sources = knowledge_base.search(question)
    if not sources or sources[0].distance > MAX_RETRIEVAL_DISTANCE:
        return "《学生手册》中未查询到相关规定，请咨询辅导员。", sources, True
    if not deepseek_api_key.strip():
        raise RagError("已找到相关规定，请在侧边栏填写 DeepSeek API Key 后生成回答。")

    context = "\n\n".join(
        f"[材料 {index}] 来源：《{source.source_name}》第 {source.page} 页 {source.article}\n"
        f"{source.text}"
        for index, source in enumerate(sources, start=1)
    )
    recent_history = list(history)[-6:]
    dialogue = "\n".join(
        f"{message['role']}：{message['content']}" for message in recent_history
    ) or "（无）"
    system_prompt = """你是广州应用科技学院的校务助手。只能依据“检索材料”回答，不能使用常识、猜测、对话历史或材料外信息补充规定。
若检索材料不能完整支持答案，必须只回答：“《学生手册》中未查询到相关规定，请咨询辅导员。”
不要编造页码、条款、处分标准或办理流程。回答采用清晰、简洁的中文；对话历史只用于理解“它、这个”等指代，不能作为事实依据。
不要在回答末尾自行编造引用；程序会附加可验证的原文依据。"""
    user_prompt = f"""检索材料：
{context}

最近对话（仅用于理解指代）：
{dialogue}

当前问题：{question}
"""
    try:
        client = OpenAI(api_key=deepseek_api_key.strip(), base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            temperature=0.1,
            max_tokens=900,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        answer = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        raise RagError(f"DeepSeek 调用失败：{exc}") from exc

    refusal = "未查询到相关规定" in answer
    if refusal:
        return "《学生手册》中未查询到相关规定，请咨询辅导员。", sources, True

    citations = "\n\n".join(f"- {source.citation}" for source in sources)
    return f"{answer}\n\n**依据引用**\n{citations}", sources, False
