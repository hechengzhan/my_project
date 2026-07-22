from pathlib import Path


def load_text_files(directory: Path):
    """递归读取目录中的 .txt 和 .md 文本资料。"""
    if not directory.exists():
        return []

    files = []
    for path in directory.rglob("*"):
        if path.suffix.lower() not in {".txt", ".md"}:
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            text = path.read_text(encoding="gbk", errors="ignore").strip()

        if text:
            files.append({
                "path": str(path),
                "text": text,
            })

    return files
