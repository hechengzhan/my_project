# 青柠校园集

广州应用科技学院校园二手交易与 AI 智能估价平台。

上传 1-3 张商品图片后，系统会识别商品、分析成色、推荐价格并生成校园交易文案。配置通义千问 API Key 后可使用真实图片识别；未配置时，系统会启用模拟估价，商品发布、搜索与管理功能仍可正常体验。

## 功能

- AI 智能发品：图片识别、分类、成色、价格、标签和交易文案生成。
- 商品集市：卡片流、分类筛选、关键词搜索与已售出展示。
- 商品详情：图片、AI 标签、完整文案和联系方式一键复制。
- 用户系统：注册、登录、JWT 鉴权、个人中心、上架/售出/下架与永久删除自己的商品。
- 内容安全：敏感词拦截、AI 审核和管理员删除违规商品。

## 技术栈

- 前端：Vue 3、Vite、Tailwind CSS
- 后端：Python 3.10、FastAPI
- 数据库：SQLite
- AI：通义千问视觉模型

## 在 VS Code 中启动

### 1. 安装软件

请安装以下软件：

1. [Python 3.10.13](https://www.python.org/downloads/release/python-31013/)。安装第一页务必勾选 **Add Python 3.10 to PATH**。
2. [Node.js 22 LTS](https://nodejs.org/)。
3. [Visual Studio Code](https://code.visualstudio.com/)。

建议在 VS Code 扩展商店安装 `Python`（Microsoft）和 `Vue - Official`。

### 2. 打开项目和终端

1. 在 VS Code 点击 **文件** → **打开文件夹**，选择本项目文件夹。
2. 点击顶部菜单 **终端** → **新建终端**。
3. 确认终端当前目录是项目根目录，即能看到 `main.py`、`requirements.txt` 和 `frontend` 文件夹。

### 3. 检查 Python

在终端输入：

```shell
python --version
```

应显示 `Python 3.10.x`。如果显示的路径或报错信息中有 `D:\BiliGame`，说明系统使用了游戏附带的 Python，不能用于本项目；请安装官方 Python 3.10.13 并重启 VS Code。

### 4. 创建 `.env`

在左侧资源管理器中，右键 `.env.example` → **复制** → 在空白处右键 **粘贴** → 将新文件重命名为 `.env`。

打开 `.env`，填写：

```env
SECRET_KEY=K8vZr2mQ7xLp4aN9cWd6Ty1Hs5Jf3Ub0Ge8Ri2Mo7Pk4Dv9Xa1Cn6Lq5Sw
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Admin123!
```

不要将 `.env` 上传到 GitHub，也不要把里面的 API Key 发给别人。

### 5. 启动后端

逐行运行：

```shell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn main:app --reload
```

看到 `Uvicorn running on http://127.0.0.1:8000`，说明后端启动成功。保持这个终端不要关闭。

如果之前创建 `.venv` 失败，请在 VS Code 左侧资源管理器中删除项目里的 `.venv` 文件夹，再重新执行上面三行命令。

### 6. 启动前端

点击终端右上角的 **+** 新开一个终端，保持后端终端继续运行。再逐行输入：

```shell
cd frontend
npm install
npm run dev
```

终端会显示一个网页地址，通常是 <http://localhost:5173>。按住 `Ctrl` 点击该地址，或复制到浏览器打开。

## 配置通义千问图片识别

1. 登录[阿里云百炼 Model Studio](https://bailian.console.aliyun.com/)，选择“华北 2（北京）”。
2. 进入 API Key 页面，创建 Key。具体可参考官方[获取 API Key 指南](https://help.aliyun.com/zh/model-studio/get-api-key)。
3. 在 `.env` 中填入：

```env
DASHSCOPE_API_KEY=sk-你的真实密钥
```

4. 保存后，在后端终端按 `Ctrl + C` 停止服务，再重新运行：

```shell
.venv\Scripts\python.exe -m uvicorn main:app --reload
```

默认模型是 `qwen3.6-flash`，支持图片理解和结构化输出。具体能力可查看[官方视觉理解文档](https://help.aliyun.com/zh/model-studio/vision-model/)。

## 数据保存在哪里

第一次启动后端后，项目根目录会自动创建 `campus_market.db`，这是 SQLite 数据库文件：

- 注册的账号保存在 `users` 表。
- 已发布的商品保存在 `listings` 表。
- 商品图片地址保存在 `listing_images` 表。
- 实际上传的图片保存在 `uploads` 文件夹。

这些是运行产生的数据，已经被 `.gitignore` 排除，不会上传到 GitHub。

## 公网部署

项目包含 [Dockerfile](Dockerfile) 与 [render.yaml](render.yaml)，可部署到 Render。Render 会通过 Docker 构建项目，成功后提供 `https://xxx.onrender.com` 公网地址，不受是否同一 Wi-Fi 限制。

部署时需要在 Render 填写：

```text
ADMIN_PASSWORD=你自己的管理员强密码
DASHSCOPE_API_KEY=你的百炼API密钥
```

`SECRET_KEY` 会由 `render.yaml` 自动生成。项目使用 `/data` 持久化磁盘保存 SQLite 数据库和上传图片；Render 的持久化磁盘需要使用付费 Web Service。详细操作可查看 [Render FastAPI 部署文档](https://render.com/docs/deploy-fastapi)。

## 常见问题

### `python -m venv .venv` 报错且出现 `D:\BiliGame`

安装官方 Python 3.10.13 时勾选 **Add Python 3.10 to PATH**，完全退出并重新打开 VS Code；然后删除项目内创建失败的 `.venv` 文件夹，再重新启动后端。

### `npm` 不是命令

说明 Node.js 没有正确安装。安装 Node.js 22 LTS 后，完全退出并重新打开 VS Code。

### 显示“模拟估价”

检查 `.env` 中是否填写 `DASHSCOPE_API_KEY`，保存后重启后端。打开 <http://127.0.0.1:8000/api/health>，若看到 `"ai_enabled": true`，代表 Key 已被读取。

### 前端打开但发布失败

确认后端终端仍在运行，并且浏览器打开的是前端终端显示的 `localhost:5173` 地址。
