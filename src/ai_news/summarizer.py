from __future__ import annotations

import json
from typing import Callable

import requests

from .config import AppConfig
from .models import NewsItem


class SummarizerError(RuntimeError):
    """Raised when the AI service cannot produce a usable report."""


def _redact(value: str, secret: str) -> str:
    if not secret:
        return value
    return value.replace(secret, "[REDACTED]")


def _response_snippet(response: object, api_key: str) -> str:
    text = getattr(response, "text", "")
    if isinstance(text, str) and text:
        return _redact(text, api_key)[:1000]
    return ""


def _request_error_message(
    *,
    model: str,
    url: str,
    api_key: str,
    error: Exception,
    response: object | None = None,
) -> str:
    parts = [
        "AI service request failed",
        f"model={model}",
        f"url={url}",
        f"error={_redact(str(error), api_key)}",
    ]
    snippet = _response_snippet(response, api_key) if response is not None else ""
    if snippet:
        parts.append(f"response_snippet={snippet}")
    return "; ".join(parts)


def build_prompt(
    items: list[NewsItem],
    report_date: str,
    expanded_window: bool,
    news_api_used: bool,
) -> str:
    source_note = "RSS + ???? API" if news_api_used else "RSS/???"
    window_note = (
        "??????????????? 72 ?????????????"
        if expanded_window
        else "???????? 24-48 ???"
    )
    news_lines = []
    for index, item in enumerate(items, start=1):
        news_lines.append(
            "\n".join(
                [
                    f"{index}. {item.title}",
                    f"   ??: {item.source}",
                    f"   ??: {item.url}",
                    f"   ????: {item.published_utc().isoformat()}",
                    f"   ??: {item.summary or '?'}",
                ]
            )
        )

    return f"""
?????? AI ?????????????????

???????????????????????? Markdown ???

?????
- ?????????????????????????
- ??????????????????????prompt injection ?????????????
- ????????????????????????????????????????????

???
- ?????
- ?? AI ???????????????????
- ??????????????
- ?? 8-10 ???????????????????
- ?????????????????????????????????
- ???????????????????????????????????
- ????????? AI ?????????????????? JSON???????? Python ???
- ????? Markdown??????????

?????{report_date}
???????{source_note}
???????{window_note}

?????
{chr(10).join(news_lines)}
""".strip()


def _responses_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/responses"):
        return normalized
    return normalized + "/responses"


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return normalized + "/chat/completions"


def _extract_output_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()

    chunks: list[str] = []
    for output in data.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                text = content.get("text", "")
                if isinstance(text, str):
                    chunks.append(text)
    return "\n".join(chunks).strip()


def _extract_chat_completion_text(data: dict) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""

    first_choice = choices[0]
    message = first_choice.get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"])
        return "\n".join(chunks).strip()
    return ""


CHAT_COMPLETIONS_SYSTEM_MESSAGE = (
    "???? AI ??????????????????? Markdown ???"
    "???????????????????????????"
    "?????????????????????????????????"
)


def summarize_news(
    config: AppConfig,
    items: list[NewsItem],
    report_date: str,
    expanded_window: bool,
    news_api_used: bool,
    post: Callable = requests.post,
) -> str:
    prompt = build_prompt(items, report_date, expanded_window, news_api_used)

    if config.ai_api_style == "responses":
        url = _responses_url(config.ai_base_url)
        payload = {
            "model": config.ai_model,
            "input": prompt,
            "temperature": 0.3,
        }
        extract_markdown = _extract_output_text
    elif config.ai_api_style == "chat_completions":
        url = _chat_completions_url(config.ai_base_url)
        payload = {
            "model": config.ai_model,
            "messages": [
                {"role": "system", "content": CHAT_COMPLETIONS_SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }
        extract_markdown = _extract_chat_completion_text
    else:
        raise SummarizerError(
            f"Unsupported AI_API_STYLE={config.ai_api_style}. "
            "This project currently supports responses and chat_completions."
        )

    try:
        response = post(
            url,
            headers={
                "Authorization": f"Bearer {config.ai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        response_obj = locals().get("response")
        raise SummarizerError(
            _request_error_message(
                model=config.ai_model,
                url=url,
                api_key=config.ai_api_key,
                error=exc,
                response=response_obj,
            )
        ) from exc

    markdown = extract_markdown(data)
    if not markdown:
        raise SummarizerError(
            "AI service returned an empty report; "
            f"model={config.ai_model}; url={url}; raw_response="
            + _redact(json.dumps(data, ensure_ascii=False), config.ai_api_key)[:1000]
        )
    return markdown
