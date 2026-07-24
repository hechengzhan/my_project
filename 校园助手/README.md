# 广应科校园智能校务助手

一个基于 **Streamlit + ChromaDB + RAG** 的本地校园制度问答 MVP。它会从《学生手册》和用户上传的 PDF 中检索 Top-3 原文片段，再交由 DeepSeek 作答；当证据不足时，会直接拒答，避免产生幻觉。

## 已实现功能

- Streamlit 聊天界面与会话历史；蓝白渐变校园风格和学校 Logo。
- 侧边栏动态输入 DeepSeek / DashScope API Key，密钥不写入源码、不保存到磁盘。
- 默认读取项目根目录的学生手册 PDF，按约 **450 字符**切块、**50 字符**重叠。
- 通过 DashScope `text-embedding-v4` 构建 ChromaDB 持久化向量索引，并由 DeepSeek `deepseek-v4-flash` 生成回答。
- 检索 Top-3 片段，低于相关度阈值时拒答：`《学生手册》中未查询到相关规定，请咨询辅导员。`
- 每次回复附带“依据引用”，并在“依据溯源”折叠面板中显示页码、条款、原始片段和相似距离。
- 支持上传多个补充 PDF，自动保存到本地并与学生手册共同检索；下次启动无需重复向量化。

## 运行环境

- Windows
- Python **3.10.13**（本机可用路径：`D:\BiliGame\envs\py310\python.exe`）
- 可访问 DeepSeek 与阿里云 DashScope API

## 准备学生手册 PDF

项目不包含《学生手册》PDF，也不会将 PDF 上传到 GitHub。克隆项目后，请自行把学校提供的学生手册 PDF 放到项目根目录（即与 `app.py` 同一层）。

文件名可以自行命名；程序会优先寻找名称中含“学生手册”的 PDF。首次点击“构建 / 更新学生手册”后，系统会在本地生成向量索引。

## 首次运行

在项目根目录打开 PowerShell，依次运行：

```powershell
& 'D:\BiliGame\envs\py310\python.exe' -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py
```

如果 PowerShell 阻止激活虚拟环境，先在当前窗口运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

浏览器打开后：

1. 在左侧填入 DeepSeek API Key 和 DashScope Embedding API Key；如果控制台显示业务空间 ID，也一并填入第三个可选输入框。
2. 点击“构建 / 更新学生手册”。首次构建会调用 Embedding API，完成后索引保存在 `data/chroma/`。
3. 在底部输入问题开始对话。后续启动时，只要 PDF 未变化，不会重复向量化。

## 需要准备的 API Key

| 用途 | 服务 | 模型 | 需要填写的位置 |
| --- | --- | --- | --- |
| 回答生成 | DeepSeek | `deepseek-v4-flash` | `DeepSeek API Key` |
| 文本向量化 | 阿里云 DashScope | `text-embedding-v4` | `DashScope Embedding API Key` |

两个 Key 和可选业务空间 ID都只保留在当前浏览器会话中。请勿把 Key 写入 `app.py`、截图、Git 仓库或提交记录。DeepSeek 使用 OpenAI 兼容地址；DashScope 支持 OpenAI 兼容的 Embedding 接口。可分别查阅 [DeepSeek 官方调用说明](https://api-docs.deepseek.com/guides/function_calling/) 和 [DashScope 官方 Embedding 说明](https://help.aliyun.com/zh/model-studio/embedding-interfaces-compatible-with-openai/)。

## 项目文件

```text
校园助手/
├─ app.py                 # Streamlit 页面和交互逻辑
├─ rag_engine.py          # PDF 解析、ChromaDB、检索、DeepSeek 调用
├─ school_logo.png        # 学校 Logo
├─ requirements.txt       # 依赖清单
├─ 你的学生手册.pdf        # 需自行放入；已被 Git 忽略，不会上传
├─ data/                  # 运行后自动生成的本地向量库（不提交）
└─ uploads/               # 用户上传并持久保存的 PDF（不提交）
```

## 防幻觉规则

系统使用 ChromaDB cosine distance 判断检索结果。最相关文本块的距离大于 `0.48` 时，或模型明确判断资料无法支持答案时，系统会拒绝回答。DeepSeek 的系统提示词同时禁止使用材料外的常识、猜测或历史对话补充规定。

> 提示：引用中的“第 X 条”来自 PDF 正文自动识别；目录、附录等没有标注条款的内容会显示“未标注条款”，不会虚构条款号。
