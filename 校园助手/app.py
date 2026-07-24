"""基于 Streamlit + ChromaDB + DeepSeek 的校园智能校务助手。"""

from __future__ import annotations

import streamlit as st

from rag_engine import KnowledgeBase, RagError, answer_question, find_student_handbook


st.set_page_config(
    page_title="广应科校园智能校务助手",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_style() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(135deg, #f9fcff 0%, #e8f3ff 52%, #d9ecff 100%);
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0a4fb3 0%, #1769e0 58%, #4a9bf5 100%);
        }
        [data-testid="stSidebar"] * { color: #ffffff; }
        [data-testid="stSidebar"] input { color: #102a43 !important; background: #ffffff !important; }
        [data-testid="stSidebar"] button,
        [data-testid="stSidebar"] button *,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button * {
            color: #0b57c6 !important;
        }
        [data-testid="stSidebar"] .stButton button,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button {
            background: #ffffff !important; border: 0; font-weight: 700;
        }
        /* 帮助提示图标与上方输入框保持同一套深蓝透明样式。 */
        [data-testid="stSidebar"] [data-testid="stTooltipHoverTarget"],
        [data-testid="stSidebar"] [data-testid="stTooltipHoverTarget"] button,
        [data-testid="stSidebar"] [data-testid="stTooltipHoverTarget"] button *,
        [data-testid="stSidebar"] [data-testid="stTooltipIcon"],
        [data-testid="stSidebar"] [data-testid="stTooltipIcon"] * {
            background: transparent !important;
            color: #074d9c !important;
            border-color: #074d9c !important;
        }
        /* 上传按钮固定在白色上传框的几何中心。 */
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section {
            position: relative;
            min-height: 122px;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section > span {
            position: absolute;
            inset: 0;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section > span > div {
            display: none !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section > span button {
            margin: 0 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section small {
            position: absolute;
            z-index: 1;
            left: 0;
            right: 0;
            bottom: .55rem;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] small,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzoneInstructions"] {
            color: rgba(255, 255, 255, .82) !important;
            text-align: center;
        }
        /* 收起按钮保持 Streamlit 原有的简洁外观，仅提亮图标。 */
        [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button,
        [data-testid="stSidebar"] button[aria-label*="sidebar"],
        [data-testid="stSidebar"] button[aria-label*="侧边栏"] {
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button *,
        [data-testid="stSidebar"] button[aria-label*="sidebar"] *,
        [data-testid="stSidebar"] button[aria-label*="侧边栏"] * {
            color: #ffffff !important;
            fill: #ffffff !important;
            opacity: 1 !important;
        }
        .hero {
            background: rgba(255,255,255,.82); border: 1px solid rgba(40,120,220,.16);
            border-radius: 20px; padding: 1.25rem 1.5rem; margin-bottom: 1rem;
            box-shadow: 0 10px 32px rgba(25, 100, 190, .10);
        }
        .hero h1 { color: #0b4fae; margin: 0 0 .2rem 0; font-size: 2rem; }
        .hero p { color: #4a6178; margin: 0; }
        .logo-wrap { display:flex; align-items:center; height: 76px; }
        .logo-wrap img { max-height: 74px; max-width: 100%; object-fit: contain; }
        .stChatMessage { border-radius: 16px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session() -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("notice", "")


def render_sidebar() -> tuple[str, str, str, list, bool]:
    with st.sidebar:
        st.markdown("## ⚙️ 安全配置")
        st.caption("密钥仅用于本次运行，不会写入文件或数据库。")
        deepseek_key = st.text_input("DeepSeek API Key", type="password", key="deepseek_key")
        dashscope_key = st.text_input(
            "DashScope Embedding API Key", type="password", key="dashscope_key"
        )
        workspace_id = st.text_input(
            "DashScope 业务空间 ID（可选）",
            help="填写后使用阿里云百炼推荐的专属域名；留空仍可使用兼容地址。",
        )
        st.markdown("---")
        st.markdown("## 📚 知识库管理")
        handbook = find_student_handbook()
        if handbook:
            st.caption(f"默认文档：{handbook.name}")
        else:
            st.warning("根目录中未找到默认学生手册 PDF。")

        build_handbook = st.button("构建 / 更新学生手册", use_container_width=True)
        uploaded_files = st.file_uploader(
            "上传补充 PDF（自动持久化入库）",
            type=["pdf"],
            accept_multiple_files=True,
            help="上传文件会与学生手册共同检索；关闭程序后仍会保留。",
        )
        if st.button("清空对话", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
        st.markdown("---")
    return deepseek_key, dashscope_key, workspace_id, uploaded_files, build_handbook


def index_documents(
    dashscope_key: str, workspace_id: str, build_handbook: bool, uploaded_files: list
) -> None:
    """处理按钮建库与上传即入库，两种操作都会跳过未变化文件。"""
    if not (build_handbook or uploaded_files):
        return
    if not dashscope_key.strip():
        st.session_state.notice = "请先填写 DashScope Embedding API Key，才能构建或更新知识库。"
        return

    try:
        kb = KnowledgeBase(dashscope_key, workspace_id)
        messages: list[str] = []
        with st.spinner("正在解析 PDF、切分文本并写入本地向量库…"):
            if build_handbook:
                handbook = find_student_handbook()
                if handbook is None:
                    raise RagError("项目根目录未找到学生手册 PDF。")
                messages.append(kb.index_document(handbook, "广应科学生手册"))
            for uploaded_file in uploaded_files:
                saved_path = kb.save_uploaded_pdf(uploaded_file.name, uploaded_file.getvalue())
                messages.append(kb.index_document(saved_path, uploaded_file.name.rsplit(".", 1)[0]))
        st.session_state.notice = "\n".join(messages)
    except RagError as exc:
        st.session_state.notice = str(exc)


def render_message(message: dict) -> None:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and message.get("sources"):
            render_sources(message["sources"])


def render_sources(sources: list[dict]) -> None:
    """统一渲染当前回答的原文溯源，避免历史和即时回答样式不一致。"""
    with st.expander("依据溯源（本次检索到的原始文本）"):
        for index, source in enumerate(sources, start=1):
            st.markdown(
                f"**材料 {index}｜《{source['source_name']}》"
                f"第 {source['page']} 页 {source['article']}**  "
                f"\n\n{source['text']}"
            )


def main() -> None:
    inject_style()
    init_session()
    deepseek_key, dashscope_key, workspace_id, uploaded_files, build_handbook = render_sidebar()
    index_documents(dashscope_key, workspace_id, build_handbook, uploaded_files)

    top_left, top_right = st.columns([1.35, 2.65], vertical_alignment="center")
    with top_left:
        st.image("school_logo.png", use_container_width=True)
    with top_right:
        st.markdown(
            """
            <div class="hero">
                <h1>校园智能校务助手</h1>
                <p>基于《学生手册》的可追溯问答</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if st.session_state.notice:
        st.info(st.session_state.notice)
        st.session_state.notice = ""

    for message in st.session_state.messages:
        render_message(message)

    prompt = st.chat_input("例如：考试作弊会受到什么处分？")
    if not prompt:
        return

    user_message = {"role": "user", "content": prompt}
    st.session_state.messages.append(user_message)
    render_message(user_message)
    try:
        kb = KnowledgeBase(dashscope_key, workspace_id)
        with st.chat_message("assistant"):
            with st.spinner("正在检索学生手册…"):
                answer, sources, _ = answer_question(
                    question=prompt,
                    deepseek_api_key=deepseek_key,
                    knowledge_base=kb,
                    history=st.session_state.messages[:-1],
                )
            st.markdown(answer)
            source_dicts = [
                {
                    "text": source.text,
                    "source_name": source.source_name,
                    "page": source.page,
                    "article": source.article,
                }
                for source in sources
            ]
            if source_dicts:
                render_sources(source_dicts)
        st.session_state.messages.append(
            {"role": "assistant", "content": answer, "sources": source_dicts}
        )
    except RagError as exc:
        with st.chat_message("assistant"):
            st.error(str(exc))
        st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {exc}"})


if __name__ == "__main__":
    main()
