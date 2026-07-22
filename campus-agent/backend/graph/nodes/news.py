import os
from pathlib import Path
from urllib.parse import parse_qsl

import requests
from dotenv import load_dotenv

from llm.client import call_general_llm
from llm.prompt import build_chat_prompt


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()


def news_node(state):
    """新闻节点：根据配置返回模拟新闻或调用新闻接口。"""
    query = state.get("input", "")
    provider = os.getenv("NEWS_PROVIDER", "mock").strip().lower()

    if provider == "newsapi":
        result = _query_newsapi(query)
        if result:
            if _should_fallback_to_chat(result):
                fallback = _try_chat_fallback(state, result)
                if fallback:
                    return fallback
            return {"result": result, "sources": ["newsapi"]}
        fallback = _try_chat_fallback(state, "新闻 API 未配置完整，无法查询实时新闻。")
        if fallback:
            return fallback

    if provider == "custom":
        result = _query_custom_news_api(query)
        if result:
            if _should_fallback_to_chat(result):
                fallback = _try_chat_fallback(state, result)
                if fallback:
                    return fallback
            return {"result": result, "sources": ["custom_news_api"]}
        fallback = _try_chat_fallback(state, "新闻 API 未配置完整，无法查询实时新闻。")
        if fallback:
            return fallback

    return {"result": _mock_news(), "sources": ["mock_news"]}


def _mock_news() -> str:
    """根据环境变量返回模拟新闻内容。"""
    mock = os.getenv(
        "MOCK_NEWS",
        "今日校园新闻模拟：学校近期将举行学术讲座、社团活动和就业指导分享会。"
    )
    return mock


def _query_newsapi(query: str) -> str:
    """调用 NewsAPI 兼容接口并格式化新闻结果。"""
    api_key = os.getenv("NEWS_API_KEY", "").strip()
    if not api_key:
        return ""

    base_url = os.getenv("NEWS_API_URL", "https://newsapi.org/v2/top-headlines").strip()
    country = os.getenv("NEWS_COUNTRY", "cn").strip()
    page_size = os.getenv("NEWS_PAGE_SIZE", "5").strip()
    category = _guess_newsapi_category(query)

    params = {
        "apiKey": api_key,
        "country": country,
        "pageSize": page_size,
    }
    if category:
        params["category"] = category

    try:
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as exc:
        return f"新闻 API 网络请求失败：{exc}。"
    except Exception as exc:
        return f"新闻 API 暂时不可用：{exc}。"

    if data.get("status") not in (None, "ok"):
        message = data.get("message") or data.get("msg") or "未知错误"
        return f"新闻 API 返回异常：{message}。"

    articles = data.get("articles") or []
    return _format_news_items(articles)


def _query_custom_news_api(query: str) -> str:
    """调用自定义新闻接口，支持 query 或 bearer 鉴权。"""
    api_url = os.getenv("NEWS_API_URL", "").strip()
    if not api_url:
        return ""

    api_key = os.getenv("NEWS_API_KEY", "").strip()
    key_param = os.getenv("NEWS_API_KEY_PARAM", "key").strip()
    page_size = os.getenv("NEWS_PAGE_SIZE", "5").strip()

    headers = {"Accept": "application/json"}
    auth_type = os.getenv("NEWS_API_AUTH_TYPE", "query").strip().lower()
    params = {}

    if api_key and auth_type == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    elif api_key:
        params[key_param] = api_key

    params[os.getenv("NEWS_API_SIZE_PARAM", "num").strip()] = page_size
    params.update(_extra_params())

    try:
        response = requests.get(api_url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as exc:
        return f"新闻 API 网络请求失败：{exc}。"
    except Exception as exc:
        return f"新闻 API 暂时不可用：{exc}。"

    items = _extract_news_items(data)
    return _format_news_items(items)


def _guess_newsapi_category(query: str) -> str:
    """根据用户关键词推测 NewsAPI 新闻分类。"""
    mapping = {
        "科技": "technology",
        "技术": "technology",
        "体育": "sports",
        "财经": "business",
        "商业": "business",
        "娱乐": "entertainment",
        "健康": "health",
        "科学": "science",
    }
    for keyword, category in mapping.items():
        if keyword in query:
            return category
    return ""


def _extract_news_items(data):
    """从不同新闻接口返回结构中提取新闻列表。"""
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    if isinstance(data.get("articles"), list):
        return data["articles"]

    if isinstance(data.get("newslist"), list):
        return data["newslist"]

    result = data.get("result")
    if isinstance(result, dict):
        if isinstance(result.get("newslist"), list):
            return result["newslist"]
        if isinstance(result.get("data"), list):
            return result["data"]

    if isinstance(data.get("data"), list):
        return data["data"]

    return []


def _format_news_items(items) -> str:
    """把新闻列表整理成适合前端展示的文本。"""
    if not items:
        return "暂时没有查到相关新闻。"

    lines = ["为你找到以下新闻："]
    for index, item in enumerate(items[:5], start=1):
        title = _pick(item, ["title", "name", "headline"]) or "未命名新闻"
        source = _extract_source(item)
        published_at = _pick(item, ["publishedAt", "ctime", "time", "date", "publish_time"])
        url = _pick(item, ["url", "link", "sourceUrl"])

        detail = f"{index}. {title}"
        extra = "，".join(part for part in [source, published_at] if part)
        if extra:
            detail += f"（{extra}）"
        if url:
            detail += f"\n   链接：{url}"
        lines.append(detail)

    return "\n".join(lines)


def _pick(item, keys):
    """按候选字段名从新闻项中取第一个非空字符串。"""
    if not isinstance(item, dict):
        return ""
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_source(item) -> str:
    """从新闻项中提取来源名称。"""
    if not isinstance(item, dict):
        return ""
    source = item.get("source")
    if isinstance(source, dict):
        return source.get("name", "") or source.get("title", "")
    if isinstance(source, str):
        return source
    return _pick(item, ["source_name", "media", "from"])


def _should_fallback_to_chat(result: str) -> bool:
    """判断新闻查询结果是否异常，是否需要大模型兜底。"""
    markers = [
        "新闻 API 网络请求失败",
        "新闻 API 暂时不可用",
        "新闻 API 返回异常",
        "暂时没有查到相关新闻",
    ]
    return any(marker in result for marker in markers)


def _try_chat_fallback(state, news_error: str):
    """新闻接口失败时，调用 DeepSeek 给出说明性回答。"""
    prompt = build_chat_prompt(
        question=(
            f"{state.get('input', '')}\n\n"
            f"说明：新闻模块没有成功返回可靠结果，错误信息是：{news_error}"
            "请你作为通用大模型，尽量给出有帮助的回答；如果无法获取实时新闻，请说明需要以官方新闻源为准。"
        ),
        history=state.get("history", ""),
    )

    answer = call_general_llm(prompt, session_id=state.get("session_id"))
    if _deepseek_fallback_failed(answer):
        return None

    return {
        "result": answer,
        "sources": ["deepseek_fallback"],
    }


def _deepseek_fallback_failed(answer: str) -> bool:
    """判断新闻模块中的 DeepSeek 兜底是否失败。"""
    markers = [
        "DeepSeek API 调用失败",
        "当前无法连接 DeepSeek 模型服务",
        "请先配置 DEEPSEEK",
    ]
    return any(marker in answer for marker in markers)


def _extra_params():
    """解析 NEWS_API_EXTRA_PARAMS 中配置的额外 URL 参数。"""
    raw = os.getenv("NEWS_API_EXTRA_PARAMS", "").strip()
    if not raw:
        return {}

    return {
        key: value
        for key, value in parse_qsl(raw, keep_blank_values=False)
        if key
    }
