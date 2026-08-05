from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .config import AppConfig, load_config
from .email_sender import send_email
from .news_sources import fetch_all_news, filter_recent_items, rank_items
from .report_store import save_report
from .summarizer import SummarizerError, summarize_news


def _report_timezone():
    try:
        return ZoneInfo("Asia/Shanghai")
    except Exception:
        return timezone(timedelta(hours=8), "Asia/Shanghai")


REPORT_TIMEZONE = _report_timezone()
NO_NEWS_TROUBLESHOOTING = (
    "No AI news items were found. Check RSS source availability, "
    "NEWS_API_PROVIDER/NEWS_API_KEY configuration, and network access."
)
CLI_TROUBLESHOOTING = (
    "Troubleshooting: verify RSS feeds are reachable, NEWS_API_PROVIDER and "
    "NEWS_API_KEY are configured when using a news API, and network access is available."
)


def report_context(
    today: date | None = None,
    now: datetime | None = None,
) -> tuple[date, str, datetime]:
    if today is None:
        current = now or datetime.now(REPORT_TIMEZONE)
        report_day = current.astimezone(REPORT_TIMEZONE).date()
    else:
        report_day = today

    report_date = report_day.isoformat()
    report_end_beijing = datetime.combine(
        report_day,
        time(23, 59, 59),
        tzinfo=REPORT_TIMEZONE,
    )
    report_end_utc = report_end_beijing.astimezone(timezone.utc)
    return report_day, report_date, report_end_utc


def _redact_secrets(message: str, config: AppConfig | None) -> str:
    if config is None:
        return message

    redacted = message
    for secret in (config.ai_api_key, config.mail_password, config.news_api_key):
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


def build_fallback_report(
    items: list[NewsItem],
    report_date: str,
    expanded_window: bool,
    news_api_used: bool,
) -> str:
    source_note = "RSS + 新闻搜索 API" if news_api_used else "RSS/公开源"
    window_note = "已扩展到最近 72 小时" if expanded_window else "最近 24-48 小时"
    lines = [
        f"# AI 新闻简报 - {report_date}",
        "",
        "> AI 总结服务暂时不可用，本报告使用自动模板生成。新闻链接和来源仍保留，便于你继续阅读。",
        "",
        "## 今日速览",
        f"- 本次筛选出 {len(items)} 条 AI 新闻。",
        f"- 来源策略：{source_note}。",
        f"- 时间窗口：{window_note}。",
        "- 建议先关注每条新闻涉及的是模型能力、数据标注、评估、安全还是产品应用。",
        "",
        "## 重点新闻",
    ]

    for index, item in enumerate(items, start=1):
        summary = item.summary or "原始来源未提供摘要，请打开链接查看详情。"
        lines.extend(
            [
                "",
                f"### {index}. {item.title}",
                f"- **来源**：{item.source}",
                f"- **链接**：{item.url}",
                f"- **发布时间**：{item.published_utc().isoformat()}",
                f"- **摘要**：{summary}",
                "- **初学者学习提示**：记录这条新闻和提示词、数据、评估或安全的关系，整理成一个可复用的问题。",
            ]
        )

    lines.extend(
        [
            "",
            "## 今日概念补充",
            "- **兜底报告**：当模型服务不可用时，系统使用固定模板保留关键信息，避免自动化任务失败。",
            "",
            "## 代码示例",
            "```python",
            "record = {",
            '    "title": "新闻标题",',
            '    "source": "新闻来源",',
            '    "trainer_note": "这条新闻对 AI 训练师有什么学习价值",',
            "}",
            "```",
            "",
            "## 延伸阅读",
            "- 优先打开上方每条新闻的原始链接，核对事实后再做学习笔记。",
        ]
    )
    return "\n".join(lines) + "\n"


def run(
    config: AppConfig,
    today: date | None = None,
    root: Path | str = ".",
    fetch_news: Callable = fetch_all_news,
    summarize: Callable = summarize_news,
    send: Callable = send_email,
) -> Path:
    _report_day, report_date, report_end = report_context(today=today)

    fetched_items, metadata = fetch_news(config)
    recent_items, expanded_window = filter_recent_items(
        fetched_items,
        min_items=8,
        now=report_end,
    )
    ranked_items = rank_items(recent_items, limit=10)
    if not ranked_items:
        raise RuntimeError(NO_NEWS_TROUBLESHOOTING)

    news_api_used = bool(metadata.get("news_api_used"))
    try:
        markdown = summarize(
            config,
            ranked_items,
            report_date,
            expanded_window,
            news_api_used,
        )
    except SummarizerError:
        print("AI 总结服务暂时不可用；已生成中文自动模板简报。", file=sys.stderr)
        markdown = build_fallback_report(
            ranked_items,
            report_date,
            expanded_window,
            news_api_used,
        )
    path = save_report(markdown, report_date, root=root)

    if config.dry_run:
        print(f"Dry run enabled; email skipped. Report saved to {path}")
    else:
        send(config, markdown, report_date)
        print(f"Email sent to {config.mail_to}. Report saved to {path}")

    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and email a daily AI news report.")
    parser.add_argument("--dry-run", action="store_true", help="Generate Markdown without sending email.")
    parser.add_argument(
        "--report-date",
        help="Generate the report for a specific Beijing date, formatted as YYYY-MM-DD.",
    )
    args = parser.parse_args()

    config = None
    try:
        config = load_config(dry_run_override=True if args.dry_run else None)
        today = date.fromisoformat(args.report_date) if args.report_date else None
        if today is None:
            run(config)
        else:
            run(config, today=today)
    except ValueError as exc:
        print("Error: --report-date must use YYYY-MM-DD format.", file=sys.stderr)
        raise SystemExit(2) from exc
    except Exception as exc:
        print(f"Error: {_redact_secrets(str(exc), config)}", file=sys.stderr)
        print(CLI_TROUBLESHOOTING, file=sys.stderr)
        raise SystemExit(1) from exc

    raise SystemExit(0)


if __name__ == "__main__":
    main()
