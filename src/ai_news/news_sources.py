from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

import feedparser
import requests

from .config import AppConfig
from .models import NewsItem, normalize_title


DEFAULT_RSS_FEEDS: list[tuple[str, str]] = [
    ("OpenAI Blog", "https://openai.com/news/rss.xml"),
    ("Google DeepMind Blog", "https://deepmind.google/blog/rss.xml"),
    ("Google AI Blog", "https://blog.google/technology/ai/rss/"),
    ("Anthropic News", "https://www.anthropic.com/news/rss.xml"),
    ("Microsoft AI Blog", "https://blogs.microsoft.com/ai/feed/"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("Planet AI Aggregate", "https://planet-ai.net/rss.xml"),
    ("The Batch", "https://www.deeplearning.ai/the-batch/rss.xml"),
    ("MIT News AI", "https://news.mit.edu/rss/topic/artificial-intelligence2"),
]

TRAINER_KEYWORDS = {
    "ai": 2,
    "llm": 3,
    "model": 2,
    "openai": 3,
    "anthropic": 3,
    "deepmind": 3,
    "hugging face": 3,
    "prompt": 4,
    "prompt engineering": 5,
    "data labeling": 5,
    "annotation": 4,
    "evaluation": 5,
    "benchmark": 4,
    "safety": 4,
    "alignment": 4,
    "multimodal": 3,
    "agent": 3,
}
US_AI_TRIO_TERMS = {
    "openai",
    "chatgpt",
    "gpt",
    "google ai",
    "google deepmind",
    "deepmind",
    "gemini",
    "anthropic",
    "claude",
}

_WORD_PATTERN = re.compile(r"[a-z0-9]+")


class NewsSourceError(RuntimeError):
    """Raised when a configured external news source fails."""


def _entry_datetime(entry: Mapping[str, Any]) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
    return datetime.now(timezone.utc)


def parse_feed_entries(source_name: str, entries: Iterable[Mapping[str, Any]]) -> list[NewsItem]:
    items: list[NewsItem] = []
    for entry in entries:
        title = str(entry.get("title", "")).strip()
        url = str(entry.get("link", "")).strip()
        if not title or not url:
            continue
        items.append(
            NewsItem(
                title=title,
                url=url,
                source=source_name,
                published_at=_entry_datetime(entry),
                summary=str(entry.get("summary", "")).strip(),
            )
        )
    return items


def fetch_news_api_items(config: AppConfig) -> list[NewsItem]:
    if not config.news_api_provider or not config.news_api_key:
        return []

    provider = config.news_api_provider.lower()
    if provider != "newsapi":
        print(f"Unsupported NEWS_API_PROVIDER={config.news_api_provider}; skipping news API.")
        return []

    query = '(AI OR "artificial intelligence" OR LLM OR "prompt engineering" OR "model evaluation")'
    try:
        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 20,
                "apiKey": config.news_api_key,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "error":
            message = str(data.get("message") or "unknown error")
            raise NewsSourceError(f"NewsAPI returned an error: {message}")
    except NewsSourceError:
        raise
    except Exception as exc:
        raise NewsSourceError("Configured NewsAPI source failed.") from exc

    items: list[NewsItem] = []
    for article in data.get("articles", []):
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        if not title or not url:
            continue
        published_raw = str(article.get("publishedAt") or "")
        try:
            published = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
        except ValueError:
            published = datetime.now(timezone.utc)
        source = article.get("source") or {}
        items.append(
            NewsItem(
                title=title,
                url=url,
                source=str(source.get("name") or "NewsAPI"),
                published_at=published,
                summary=str(article.get("description") or "").strip(),
            )
        )
    return items


def fetch_all_news(
    config: AppConfig,
    rss_feeds: list[tuple[str, str]] | None = None,
    feed_parser=feedparser.parse,
) -> tuple[list[NewsItem], dict[str, bool]]:
    feeds = rss_feeds or DEFAULT_RSS_FEEDS
    items: list[NewsItem] = []

    for source_name, url in feeds:
        try:
            parsed_feed = feed_parser(url)
            items.extend(parse_feed_entries(source_name, parsed_feed.entries))
        except Exception as exc:
            print(f"RSS source failed: {source_name} ({url}) - {exc}")

    api_items = fetch_news_api_items(config)

    all_items = dedupe_items([*items, *api_items])
    return all_items, {"news_api_used": bool(api_items)}


def dedupe_items(items: Iterable[NewsItem]) -> list[NewsItem]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    result: list[NewsItem] = []

    for item in items:
        url_key = item.url.strip().lower()
        title_key = normalize_title(item.title)
        if not url_key or not title_key:
            continue
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        result.append(item)

    return result


def filter_recent_items(
    items: Iterable[NewsItem],
    min_items: int = 8,
    now: datetime | None = None,
) -> tuple[list[NewsItem], bool]:
    current = now or datetime.now(timezone.utc)
    current = current.astimezone(timezone.utc)
    sorted_items = sorted(items, key=lambda news: news.published_utc(), reverse=True)

    recent = [
        news
        for news in sorted_items
        if timedelta(0) <= current - news.published_utc() <= timedelta(hours=48)
    ]
    if len(recent) >= min_items:
        return recent, False

    expanded = [
        news
        for news in sorted_items
        if timedelta(0) <= current - news.published_utc() <= timedelta(hours=72)
    ]
    return expanded, True


def _normalized_words(text: str) -> list[str]:
    return _WORD_PATTERN.findall(text.lower())


def _matches_keyword(keyword: str, words: list[str], normalized_text: str) -> bool:
    keyword_words = _normalized_words(keyword)
    if len(keyword_words) > 1:
        return f" {' '.join(keyword_words)} " in normalized_text
    if not keyword_words:
        return False
    keyword_word = keyword_words[0]
    return any(
        word == keyword_word and (index == 0 or words[index - 1] != "not")
        for index, word in enumerate(words)
    )


def _score_item(item: NewsItem) -> int:
    words = _normalized_words(f"{item.title} {item.summary} {item.source}")
    normalized_text = f" {' '.join(words)} "
    score = 0
    for keyword, weight in TRAINER_KEYWORDS.items():
        if _matches_keyword(keyword, words, normalized_text):
            score += weight
    return score


def _us_ai_trio_priority(item: NewsItem) -> int:
    words = _normalized_words(f"{item.title} {item.summary} {item.source}")
    normalized_text = f" {' '.join(words)} "
    return int(any(_matches_keyword(term, words, normalized_text) for term in US_AI_TRIO_TERMS))


def rank_items(items: Iterable[NewsItem], limit: int = 10) -> list[NewsItem]:
    return sorted(
        items,
        key=lambda news: (_us_ai_trio_priority(news), _score_item(news), news.published_utc()),
        reverse=True,
    )[:limit]
