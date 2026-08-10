from datetime import datetime, timedelta, timezone

from ai_news.models import NewsItem
from ai_news.news_sources import dedupe_items, filter_recent_items, rank_items


BASE_NOW = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)


def item(title, url, hours_old=2, source="Example", summary=""):
    return NewsItem(
        title=title,
        url=url,
        source=source,
        published_at=BASE_NOW - timedelta(hours=hours_old),
        summary=summary,
    )


def test_dedupe_items_removes_duplicate_urls_and_titles():
    items = [
        item("OpenAI releases new model", "https://example.com/a"),
        item("OpenAI releases new model!", "https://example.com/b"),
        item("Different story", "https://example.com/a"),
        item("Evaluation benchmark updated", "https://example.com/c"),
    ]

    deduped = dedupe_items(items)

    assert [news.title for news in deduped] == [
        "OpenAI releases new model",
        "Evaluation benchmark updated",
    ]


def test_filter_recent_items_expands_to_72_hours_when_needed():
    items = [
        item("Recent model news", "https://example.com/recent", hours_old=3),
        item("Older evaluation news", "https://example.com/older", hours_old=60),
        item("Too old", "https://example.com/too-old", hours_old=120),
    ]

    selected, expanded = filter_recent_items(items, min_items=2, now=BASE_NOW)

    assert expanded is True
    assert [news.title for news in selected] == ["Recent model news", "Older evaluation news"]


def test_filter_recent_items_excludes_future_news():
    items = [
        item("Future model news", "https://example.com/future", hours_old=-1),
        item("Recent model news", "https://example.com/recent", hours_old=3),
    ]

    selected, expanded = filter_recent_items(items, min_items=1, now=BASE_NOW)

    assert expanded is False
    assert [news.title for news in selected] == ["Recent model news"]


def test_filter_recent_items_marks_expanded_when_attempted_without_new_items():
    items = [
        item("Recent model news", "https://example.com/recent", hours_old=3),
        item("Too old", "https://example.com/too-old", hours_old=120),
    ]

    selected, expanded = filter_recent_items(items, min_items=2, now=BASE_NOW)

    assert expanded is True
    assert [news.title for news in selected] == ["Recent model news"]


def test_rank_items_prioritizes_ai_trainer_relevant_keywords():
    items = [
        item("AI startup funding", "https://example.com/funding", summary="business"),
        item("New prompt engineering evaluation guide", "https://example.com/eval", summary="LLM evaluation"),
        item("Sports result", "https://example.com/sports", summary="not ai"),
    ]

    ranked = rank_items(items, limit=2)

    assert [news.title for news in ranked] == [
        "New prompt engineering evaluation guide",
        "AI startup funding",
    ]


def test_rank_items_prioritizes_us_ai_trio_before_other_sources():
    items = [
        item(
            "New prompt engineering evaluation benchmark",
            "https://example.com/eval",
            source="Example AI News",
            summary="LLM prompt safety alignment benchmark",
        ),
        item(
            "Claude model update",
            "https://example.com/claude",
            source="Anthropic News",
            summary="A short product update.",
        ),
        item(
            "Gemini research note",
            "https://example.com/gemini",
            source="Example Wire",
            summary="Google DeepMind shared a Gemini model note.",
        ),
        item(
            "OpenAI safety update",
            "https://example.com/openai",
            source="OpenAI Blog",
            summary="A short safety update.",
        ),
    ]

    ranked = rank_items(items, limit=4)

    assert [news.title for news in ranked][-1] == "New prompt engineering evaluation benchmark"
    assert {news.title for news in ranked[:3]} == {
        "Gemini research note",
        "OpenAI safety update",
        "Claude model update",
    }


def test_rank_items_keeps_trio_news_ordered_by_relevance_then_recency():
    items = [
        item(
            "OpenAI company note",
            "https://example.com/openai",
            source="OpenAI Blog",
            hours_old=1,
            summary="A general update.",
        ),
        item(
            "Anthropic evaluation benchmark",
            "https://example.com/anthropic",
            source="Anthropic News",
            hours_old=5,
            summary="Claude model safety evaluation benchmark.",
        ),
        item(
            "Google DeepMind prompt guide",
            "https://example.com/deepmind",
            source="Google DeepMind Blog",
            hours_old=2,
            summary="Gemini prompt engineering guide.",
        ),
    ]

    ranked = rank_items(items, limit=3)

    assert [news.title for news in ranked] == [
        "Anthropic evaluation benchmark",
        "Google DeepMind prompt guide",
        "OpenAI company note",
    ]


def test_rank_items_uses_word_boundaries_for_short_keywords():
    items = [
        item("Agency said team played against rivals", "https://example.com/sports", summary="not ai"),
        item("Market update", "https://example.com/market", hours_old=1, summary="business"),
    ]

    ranked = rank_items(items, limit=2)

    assert [news.title for news in ranked] == [
        "Market update",
        "Agency said team played against rivals",
    ]
