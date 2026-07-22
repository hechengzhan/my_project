import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from llm.client import call_general_llm
from llm.prompt import build_chat_prompt


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()


def weather_node(state):
    """天气节点：根据配置返回模拟天气或调用高德天气 API。"""
    query = state.get("input", "")
    provider = os.getenv("WEATHER_PROVIDER", "mock").strip().lower()

    if provider == "amap":
        result = _query_amap_weather(query)
        if result:
            if _should_fallback_to_chat(result):
                fallback = _try_chat_fallback(state, result)
                if fallback:
                    return fallback
            return {"result": result, "sources": ["amap_weather_api"]}

    return {"result": _mock_weather(), "sources": ["mock_weather"]}


def _mock_weather() -> str:
    """根据环境变量生成模拟天气回答。"""
    city = os.getenv("WEATHER_CITY_NAME") or os.getenv("WEATHER_CITY", "校园所在地")
    weather = os.getenv("MOCK_WEATHER", "多云，气温 26°C，适合出行")
    return f"{city} 当前天气：{weather}。"


def _query_amap_weather(query: str) -> str:
    """调用高德天气 API，按用户问题返回实时天气或预报。"""
    api_key = os.getenv("AMAP_WEATHER_KEY", "").strip()
    city_code = os.getenv("WEATHER_CITY_CODE", "").strip()
    city_name = os.getenv("WEATHER_CITY_NAME", os.getenv("WEATHER_CITY", "校园所在地")).strip()

    if not api_key or not city_code:
        return ""

    needs_forecast = any(word in query for word in ["明天", "后天", "未来", "预报"])
    extensions = "all" if needs_forecast else "base"

    try:
        response = requests.get(
            "https://restapi.amap.com/v3/weather/weatherInfo",
            params={
                "key": api_key,
                "city": city_code,
                "extensions": extensions,
                "output": "json",
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.ReadTimeout:
        return f"高德天气 API 连接超时，请检查网络、代理或校园网限制。先给你模拟天气：{_mock_weather()}"
    except requests.exceptions.SSLError as exc:
        return f"高德天气 API 的 HTTPS 连接失败：{exc}。先给你模拟天气：{_mock_weather()}"
    except requests.exceptions.RequestException as exc:
        return f"高德天气 API 网络请求失败：{exc}。先给你模拟天气：{_mock_weather()}"
    except Exception:
        return f"天气 API 暂时不可用，先给你模拟天气：{_mock_weather()}"

    if data.get("status") != "1":
        info = data.get("info", "未知错误")
        return f"天气 API 返回异常：{info}。先给你模拟天气：{_mock_weather()}"

    if extensions == "all":
        forecasts = data.get("forecasts") or []
        casts = forecasts[0].get("casts", []) if forecasts else []
        if not casts:
            return f"暂时没有查到{city_name}的天气预报。"

        lines = [f"{city_name}天气预报："]
        for item in casts[:3]:
            date = item.get("date", "")
            day_weather = item.get("dayweather", "")
            night_weather = item.get("nightweather", "")
            day_temp = item.get("daytemp", "")
            night_temp = item.get("nighttemp", "")
            wind = item.get("daywind", "")
            power = item.get("daypower", "")
            lines.append(
                f"{date}：白天{day_weather}，夜间{night_weather}，"
                f"{night_temp}-{day_temp}°C，{wind}风{power}级。"
            )
        return "\n".join(lines)

    lives = data.get("lives") or []
    if not lives:
        return f"暂时没有查到{city_name}的实时天气。"

    live = lives[0]
    city = live.get("city") or city_name
    weather = live.get("weather", "")
    temperature = live.get("temperature", "")
    humidity = live.get("humidity", "")
    wind_direction = live.get("winddirection", "")
    wind_power = live.get("windpower", "")
    report_time = live.get("reporttime", "")

    return (
        f"{city}当前天气：{weather}，气温{temperature}°C，"
        f"湿度{humidity}%，{wind_direction}风{wind_power}级。"
        f"\n更新时间：{report_time}"
    )


def _should_fallback_to_chat(result: str) -> bool:
    """判断天气查询结果是否异常，是否需要大模型兜底。"""
    fallback_markers = [
        "连接超时",
        "HTTPS 连接失败",
        "网络请求失败",
        "暂时不可用",
        "返回异常",
        "暂时没有查到",
        "先给你模拟天气",
    ]
    return any(marker in result for marker in fallback_markers)


def _try_chat_fallback(state, weather_error: str):
    """天气接口失败时，调用 DeepSeek 给出说明性回答。"""
    prompt = build_chat_prompt(
        question=(
            f"{state.get('input', '')}\n\n"
            f"说明：天气模块没有成功返回可靠结果，错误信息是：{weather_error}。"
            "请你作为通用大模型，尽量给出有帮助的回答；如果无法获取实时天气，请说明需要以官方天气服务为准。"
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
    """判断天气模块中的 DeepSeek 兜底是否失败。"""
    failed_markers = [
        "DeepSeek API 调用失败",
        "当前无法连接 DeepSeek 模型服务",
        "请先配置 DEEPSEEK",
    ]
    return any(marker in answer for marker in failed_markers)
