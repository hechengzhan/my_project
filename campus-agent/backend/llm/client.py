import json
import os
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()

_CONVERSATIONS = {}


def call_llm(prompt: str, session_id: Optional[str] = None) -> str:
    """
    校园知识问答模型入口：优先调用 Coze，未配置时返回模拟结果。
    """
    provider = os.getenv("LLM_PROVIDER", "coze").lower()
    token = os.getenv("COZE_API_TOKEN", "").strip()
    bot_id = os.getenv("COZE_BOT_ID", "").strip()

    if provider == "coze" and token and bot_id:
        try:
            return _call_coze(prompt, token, bot_id, session_id=session_id)
        except Exception as exc:
            return f"Coze API 调用失败：{exc}\n\n已收到你的问题，但当前无法连接真实模型。"

    return _mock_answer(prompt)


def call_general_llm(prompt: str, session_id: Optional[str] = None) -> str:
    """
    通用大模型入口：调用 DeepSeek 处理普通聊天和兜底回答。
    """
    try:
        return _call_deepseek(prompt, session_id=session_id)
    except Exception as exc:
        return f"DeepSeek API 调用失败：{exc}\n\n已收到你的问题，但当前无法连接 DeepSeek 模型服务。"


def _call_deepseek(prompt: str, session_id: Optional[str]) -> str:
    """按 OpenAI 兼容格式请求 DeepSeek 并解析回答内容。"""
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
    timeout = int(os.getenv("DEEPSEEK_TIMEOUT", "60"))

    missing = []
    if not base_url:
        missing.append("DEEPSEEK_BASE_URL")
    if not api_key:
        missing.append("DEEPSEEK_API_KEY")
    if not model:
        missing.append("DEEPSEEK_MODEL")
    if missing:
        raise RuntimeError("请先配置 " + "、".join(missing))

    api_url = base_url
    if not api_url.endswith("/chat/completions"):
        api_url = f"{api_url}/chat/completions"

    headers = {"Content-Type": "application/json"}
    headers["Authorization"] = f"Bearer {api_key}"

    response = requests.post(
        api_url,
        headers=headers,
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "stream": False,
            "user": session_id or "default",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    if isinstance(data, str):
        return data

    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if content.strip():
            return content.strip()

    for key in ["reply", "answer", "content", "message"]:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    raise RuntimeError("DeepSeek API 没有返回 choices/reply/answer/content/message 字段")


def _call_coze(prompt: str, token: str, bot_id: str, session_id: Optional[str]) -> str:
    """调用 Coze；如果会话异常，清理旧会话后重试一次。"""
    try:
        return _call_coze_once(prompt, token, bot_id, session_id=session_id)
    except RuntimeError as exc:
        if "Coze 没有返回可展示的回答" in str(exc) and session_id:
            _CONVERSATIONS.pop(session_id, None)
            return _call_coze_once(prompt, token, bot_id, session_id=session_id)
        raise


def _call_coze_once(prompt: str, token: str, bot_id: str, session_id: Optional[str]) -> str:
    """发起一次 Coze 流式会话请求，并拼接最终文本回答。"""
    base_url = os.getenv("COZE_BASE_URL", "https://api.coze.cn").rstrip("/")
    user_id = os.getenv("COZE_USER_ID", "campus-web-user")
    timeout = int(os.getenv("COZE_TIMEOUT", "60"))

    params = {}
    if session_id and _CONVERSATIONS.get(session_id):
        params["conversation_id"] = _CONVERSATIONS[session_id]

    payload = {
        "bot_id": bot_id,
        "user_id": user_id,
        "stream": True,
        "auto_save_history": True,
        "additional_messages": [
            {
                "role": "user",
                "content": prompt,
                "content_type": "text",
            }
        ],
    }

    response = requests.post(
        f"{base_url}/v3/chat",
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
        stream=True,
    )
    response.raise_for_status()
    response.encoding = "utf-8"

    parts = []
    completed_answer = ""
    fallback_contents = []
    debug_events = []

    for current_event, data_text in _iter_sse_events(response):
        if data_text == "[DONE]":
            break

        data = _decode_sse_data(data_text)
        if data is None:
            continue

        if os.getenv("COZE_DEBUG", "").strip() == "1":
            if isinstance(data, dict):
                debug_events.append({
                    "event": current_event,
                    "keys": sorted(data.keys()),
                    "type": data.get("type"),
                    "role": data.get("role"),
                    "status": data.get("status"),
                    "last_error": data.get("last_error"),
                    "content_preview": _extract_text_content(data.get("content", ""))[:80],
                })
            else:
                debug_events.append({
                    "event": current_event,
                    "data_type": type(data).__name__,
                    "preview": str(data)[:80],
                })

        if not isinstance(data, dict):
            if current_event == "conversation.message.delta":
                parts.append(str(data))
            continue

        code = data.get("code")
        if code not in (None, 0, "0"):
            raise RuntimeError(data.get("msg") or data.get("message") or data_text)

        if current_event == "conversation.chat.failed" or data.get("status") == "failed":
            last_error = data.get("last_error") or {}
            if isinstance(last_error, dict):
                error_message = (
                    last_error.get("msg")
                    or last_error.get("message")
                    or last_error.get("detail")
                    or json.dumps(last_error, ensure_ascii=False)
                )
                error_code = last_error.get("code") or last_error.get("error_code")
                if error_code:
                    raise RuntimeError(f"Coze 会话执行失败：{error_code} - {error_message}")
                raise RuntimeError(f"Coze 会话执行失败：{error_message}")

            raise RuntimeError(f"Coze 会话执行失败：{last_error or data_text}")

        conversation_id = data.get("conversation_id")
        if conversation_id and session_id:
            _CONVERSATIONS[session_id] = conversation_id

        content = _extract_text_content(data.get("content", ""))
        message_type = data.get("type", "")
        role = data.get("role", "")

        if current_event == "conversation.message.delta" and content:
            parts.append(content)
            continue

        if current_event == "conversation.message.completed" and content:
            if message_type == "answer" or role == "assistant":
                completed_answer = content or completed_answer
            else:
                fallback_contents.append(content)
            continue

        if content and current_event.startswith("conversation.message"):
            fallback_contents.append(content)

    answer = "".join(parts).strip() or completed_answer.strip() or "\n".join(fallback_contents).strip()
    if not answer:
        if os.getenv("COZE_DEBUG", "").strip() == "1":
            print("COZE_DEBUG_EVENTS=", json.dumps(debug_events, ensure_ascii=False))
        raise RuntimeError("Coze 没有返回可展示的回答")

    return answer


def _extract_text_content(content) -> str:
    """从 Coze 返回的字符串、列表或字典中提取纯文本内容。"""
    if content is None:
        return ""

    if isinstance(content, str):
        text = content.strip()
        if not text:
            return ""
        if text.startswith("{") or text.startswith("["):
            try:
                return _extract_text_content(json.loads(text))
            except json.JSONDecodeError:
                return content
        return content

    if isinstance(content, list):
        parts = [_extract_text_content(item) for item in content]
        return "".join(part for part in parts if part)

    if isinstance(content, dict):
        for key in ["text", "content", "answer", "message"]:
            value = content.get(key)
            extracted = _extract_text_content(value)
            if extracted:
                return extracted
        return ""

    return str(content)


def _iter_sse_events(response):
    """逐行解析 SSE 响应，产出事件名和 data 内容。"""
    event = ""
    data_lines = []

    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue

        line = raw_line.strip()
        if not line:
            if data_lines:
                yield event, "\n".join(data_lines)
            event = ""
            data_lines = []
            continue

        if line.startswith(":"):
            continue

        if line.startswith("event:"):
            event = line.replace("event:", "", 1).strip()
            continue

        if line.startswith("data:"):
            data_lines.append(line.replace("data:", "", 1).strip())

    if data_lines:
        yield event, "\n".join(data_lines)


def _decode_sse_data(data_text: str):
    """把 SSE data 文本解码为 JSON 对象或普通字符串。"""
    text = data_text.strip()
    if not text:
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text

    if isinstance(data, str):
        nested = data.strip()
        if nested.startswith("{") or nested.startswith("["):
            try:
                return json.loads(nested)
            except json.JSONDecodeError:
                return data

    return data


def _mock_answer(prompt: str) -> str:
    """Coze 未配置时返回本地模拟回答，保证项目可演示。"""
    return (
        "【模拟回答】\n"
        "我已经收到请求。现在还没有配置 Coze API，所以这里先返回本地模拟结果。\n\n"
        f"{prompt}"
    )
