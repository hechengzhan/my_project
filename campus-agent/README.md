# Campus Agent

广州应用科技学院校园智能服务助手，包含网页聊天界面、FastAPI 后端、LangGraph 工作流、Coze 知识库校园问答、本地临时通知检索、天气查询、新闻查询和 DeepSeek 兜底回答。

## 功能

- 闲聊：普通问题走 DeepSeek 通用模型入口。
- 天气查询：默认模拟返回，也支持配置高德开放平台天气 API。
- 新闻查询：默认模拟返回，也支持配置 NewsAPI.org 兼容接口或自定义新闻接口。
- 校园问答：通过 Coze 智能体调用你在 Coze 中绑定的长期学校资料知识库。
- 最新通知检索：把近期通知写入 `knowledge/temp`，每次校园问答都会重载近期资料，并和 Coze 知识库答案一起综合回答。
- 向量检索：默认使用轻量 hash 向量，方便离线运行；需要更好语义效果时，把 `.env` 中 `EMBEDDING_PROVIDER` 改成 `sentence_transformers`。

## 需要补充

1. 在 Coze 创建智能体，并把 `COZE_API_TOKEN`、`COZE_BOT_ID` 填入 `.env`。
2. 确认 Coze 智能体已绑定学校资料知识库，并已发布。
3. 把需要定期更新的近期通知、活动安排放到 `knowledge/temp`。
4. 如需真实天气，申请高德开放平台 Web 服务 Key，并在 `.env` 中配置天气模块。
5. 如需真实新闻，申请新闻 API Key，并在 `.env` 中配置新闻模块。

## 运行

### 本地开发

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ..\.env.example ..\.env
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

然后打开前端终端显示的本地地址，通常是 `http://127.0.0.1:5173`。

### 给其他人访问

这个项目支持前后端同源部署：前端打包后由 FastAPI 后端直接托管，别人只需要打开后端地址。

1. 打包前端：

```powershell
cd frontend
npm install
npm.cmd run build
```

2. 启动后端，监听所有网卡：

```powershell
cd ..\backend
.\venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8000
```

3. 同一局域网内的其他人访问：

```text
http://你的电脑局域网IP:8000
```

例如你的电脑 IP 是 `192.168.1.23`，别人访问：

```text
http://192.168.1.23:8000
```

如果要让非同一网络的人访问，需要把项目部署到云服务器，或者用内网穿透工具把本机 `8000` 端口映射到公网地址。

## 最新通知资料

- 本地长期校园资料不需要放进项目，长期资料放在 Coze 知识库。
- 最新通知资料不展示在前台页面，前台用户只看到聊天助手。
- 需要更新近期通知时，直接修改或替换 `knowledge/temp` 里的 `.md` / `.txt` 文件。
- 每次校园问答都会重新读取 `knowledge/temp`，不需要额外调用刷新接口。

## DeepSeek 通用大模型

普通闲聊、校园问答兜底、天气失败兜底会调用 DeepSeek。

在 `.env` 里填写：

```env
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=你的DeepSeek Key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TIMEOUT=60
```

调用格式是 OpenAI-compatible：

```json
{
  "model": "你填写的model",
  "messages": [
    {
      "role": "user",
      "content": "用户问题"
    }
  ],
  "stream": false
}
```

## 天气模块

默认不需要申请天气接口，系统会使用 `.env` 里的 `MOCK_WEATHER` 做模拟返回。

如果要接入真实天气：

```env
WEATHER_PROVIDER=amap
WEATHER_CITY_NAME=广州
WEATHER_CITY_CODE=440100
AMAP_WEATHER_KEY=你的高德Web服务Key
```

- `WEATHER_PROVIDER=mock`：使用模拟天气。
- `WEATHER_PROVIDER=amap`：调用高德天气 API。
- `WEATHER_CITY_CODE`：城市编码，例如广州是 `440100`。

如果出现 `高德天气 API 连接超时`，说明后端当前网络访问高德 HTTPS 接口不稳定。优先尝试：

1. 换成手机热点或其他网络后重启后端。
2. 检查电脑是否开了代理、校园网认证、防火墙限制。
3. 在浏览器打开 `https://restapi.amap.com/v3/weather/weatherInfo` 看能否访问。
4. 如果只是本地课程演示，也可以临时使用 `WEATHER_PROVIDER=mock` 保证功能可展示。

## 新闻模块

默认使用模拟新闻：

```env
NEWS_PROVIDER=mock
MOCK_NEWS=今日校园新闻模拟：学校近期将举行学术讲座、社团活动和就业指导分享会。
```

如果使用 NewsAPI.org 兼容接口：

```env
NEWS_PROVIDER=newsapi
NEWS_API_URL=https://newsapi.org/v2/top-headlines
NEWS_API_KEY=你的新闻API Key
NEWS_COUNTRY=cn
NEWS_PAGE_SIZE=5
```

如果你使用的是其它新闻接口，可以用自定义模式：

```env
NEWS_PROVIDER=custom
NEWS_API_URL=你的新闻接口地址
NEWS_API_KEY=你的新闻接口Key
NEWS_API_KEY_PARAM=key
NEWS_API_AUTH_TYPE=query
NEWS_API_SIZE_PARAM=num
NEWS_PAGE_SIZE=5
```

- `NEWS_API_AUTH_TYPE=query`：把 Key 放在 URL 参数里。
- `NEWS_API_AUTH_TYPE=bearer`：把 Key 放在 `Authorization: Bearer ...` 请求头里。
