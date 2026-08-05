import os
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from ai_news.config import AppConfig
from ai_news import main as main_module
from ai_news.main import report_context, run
from ai_news.models import NewsItem
from ai_news.summarizer import SummarizerError


def config(dry_run=True):
    return AppConfig(
        ai_api_key="ai-key",
        ai_base_url="https://api.example.com",
        ai_model="model",
        ai_api_style="responses",
        mail_host="smtp.163.com",
        mail_port=465,
        mail_username="sender@163.com",
        mail_password="auth",
        mail_from="sender@163.com",
        mail_to="reader@example.com",
        news_api_provider="",
        news_api_key="",
        dry_run=dry_run,
    )


def test_run_saves_report_and_skips_email_in_dry_run(tmp_path):
    calls = {"email": 0}

    def fake_fetch(_config):
        return (
            [
                NewsItem(
                    title="Prompt evaluation news",
                    url="https://example.com/eval",
                    source="Example",
                    published_at=datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc),
                    summary="Evaluation",
                )
            ],
            {"news_api_used": False},
        )

    def fake_summarize(_config, items, report_date, expanded_window, news_api_used):
        assert report_date == "2026-04-30"
        assert expanded_window is True
        assert news_api_used is False
        assert len(items) == 1
        return "# 每日 AI 热点新闻简报\n"

    def fake_send(*args, **kwargs):
        calls["email"] += 1

    path = run(
        config(dry_run=True),
        today=date(2026, 4, 30),
        root=tmp_path,
        fetch_news=fake_fetch,
        summarize=fake_summarize,
        send=fake_send,
    )

    assert calls["email"] == 0
    assert path == tmp_path / "reports" / "2026-04-30.md"
    assert path.read_text(encoding="utf-8").startswith("# 每日 AI 热点新闻简报")


def test_run_sends_email_when_not_dry_run(tmp_path):
    calls = {"email": 0}
    summarize_calls = {}

    def fake_fetch(_config):
        return (
            [
                NewsItem(
                    title=f"AI news {index}",
                    url=f"https://example.com/{index}",
                    source="Example",
                    published_at=datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc),
                    summary="AI model evaluation",
                )
                for index in range(10)
            ],
            {"news_api_used": True},
        )

    def fake_summarize(_config, items, report_date, expanded_window, news_api_used):
        summarize_calls["expanded_window"] = expanded_window
        summarize_calls["news_api_used"] = news_api_used
        return "# 简报\n"

    def fake_send(_config, markdown, report_date):
        calls["email"] += 1
        assert markdown == "# 简报\n"
        assert report_date == "2026-04-30"

    run(
        config(dry_run=False),
        today=date(2026, 4, 30),
        root=tmp_path,
        fetch_news=fake_fetch,
        summarize=fake_summarize,
        send=fake_send,
    )

    assert calls["email"] == 1
    assert summarize_calls == {"expanded_window": False, "news_api_used": True}


def test_run_sends_fallback_report_when_ai_summary_fails(tmp_path, capsys):
    calls = {}

    def fake_fetch(_config):
        return (
            [
                NewsItem(
                    title="GitHub Models retirement brownout",
                    url="https://example.com/github-models-brownout",
                    source="Example",
                    published_at=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
                    summary="GitHub Models returned 410 Gone.",
                )
            ],
            {"news_api_used": False},
        )

    def fake_summarize(*args, **kwargs):
        raise SummarizerError("github_models_retirement_brownout with ai-key")

    def fake_send(_config, markdown, report_date):
        calls["markdown"] = markdown
        calls["report_date"] = report_date

    path = run(
        config(dry_run=False),
        today=date(2026, 8, 4),
        root=tmp_path,
        fetch_news=fake_fetch,
        summarize=fake_summarize,
        send=fake_send,
    )

    captured = capsys.readouterr()
    markdown = path.read_text(encoding="utf-8")
    assert calls["report_date"] == "2026-08-04"
    assert calls["markdown"] == markdown
    assert "AI 新闻简报" in markdown
    assert "自动模板" in markdown
    assert "GitHub Models retirement brownout" in markdown
    assert "https://example.com/github-models-brownout" in markdown
    assert "AI 总结服务暂时不可用" in captured.err
    assert "ai-key" not in captured.err


def test_report_context_uses_beijing_date_and_utc_filter_anchor():
    report_day, report_date, report_end = report_context(
        now=datetime(2026, 4, 29, 16, 30, tzinfo=timezone.utc)
    )

    assert report_day == date(2026, 4, 30)
    assert report_date == "2026-04-30"
    assert report_end == datetime(2026, 4, 30, 15, 59, 59, tzinfo=timezone.utc)


def test_report_context_respects_explicit_today_for_beijing_anchor():
    report_day, report_date, report_end = report_context(today=date(2026, 4, 30))

    assert report_day == date(2026, 4, 30)
    assert report_date == "2026-04-30"
    assert report_end == datetime(2026, 4, 30, 15, 59, 59, tzinfo=timezone.utc)


def test_main_passes_report_date_argument_to_run(monkeypatch):
    captured = {}

    def fake_load_config(dry_run_override=None):
        assert dry_run_override is None
        return config(dry_run=False)

    def fake_run(_config, today=None):
        captured["today"] = today

    monkeypatch.setattr(main_module, "load_config", fake_load_config)
    monkeypatch.setattr(main_module, "run", fake_run)
    monkeypatch.setattr(
        main_module.sys,
        "argv",
        ["ai-news", "--report-date", "2026-05-03"],
    )

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == 0
    assert captured["today"] == date(2026, 5, 3)


def test_run_no_news_error_includes_actionable_troubleshooting(tmp_path):
    def fake_fetch(_config):
        return ([], {"news_api_used": False})

    with pytest.raises(RuntimeError) as exc_info:
        run(
            config(dry_run=True),
            today=date(2026, 4, 30),
            root=tmp_path,
            fetch_news=fake_fetch,
            summarize=lambda *args: "# unused\n",
            send=lambda *args: None,
        )

    message = str(exc_info.value)
    assert "RSS" in message
    assert "NEWS_API_PROVIDER" in message
    assert "NEWS_API_KEY" in message
    assert "network" in message.lower()
    assert "ai-key" not in message


def test_main_prints_friendly_error_and_exits_nonzero(monkeypatch, capsys):
    def fake_load_config(dry_run_override=None):
        assert dry_run_override is None
        return config(dry_run=False)

    def fake_run(_config):
        raise RuntimeError("No AI news items were found. Check RSS sources.")

    monkeypatch.setattr(main_module, "load_config", fake_load_config)
    monkeypatch.setattr(main_module, "run", fake_run)
    monkeypatch.setattr(main_module.sys, "argv", ["ai-news"])

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "Error: No AI news items were found." in captured.err
    assert "Troubleshooting:" in captured.err
    assert "NEWS_API_KEY" in captured.err
    assert "ai-key" not in captured.err


def test_main_redacts_configured_secrets_from_errors(monkeypatch, capsys):
    app_config = replace(config(dry_run=False), news_api_key="news-secret")

    def fake_load_config(dry_run_override=None):
        return app_config

    def fake_run(_config):
        raise RuntimeError("failed with ai-key and news-secret")

    monkeypatch.setattr(main_module, "load_config", fake_load_config)
    monkeypatch.setattr(main_module, "run", fake_run)
    monkeypatch.setattr(main_module.sys, "argv", ["ai-news"])

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "ai-key" not in captured.err
    assert "news-secret" not in captured.err
    assert "[redacted]" in captured.err


def test_module_execution_runs_cli_and_reports_missing_config():
    env = os.environ.copy()
    for key in [
        "AI_API_KEY",
        "AI_BASE_URL",
        "AI_MODEL",
        "AI_API_STYLE",
        "MAIL_HOST",
        "MAIL_PORT",
        "MAIL_USERNAME",
        "MAIL_PASSWORD",
        "MAIL_FROM",
        "MAIL_TO",
        "NEWS_API_PROVIDER",
        "NEWS_API_KEY",
        "DRY_RUN",
    ]:
        env.pop(key, None)

    result = subprocess.run(
        [sys.executable, "-m", "ai_news.main", "--dry-run"],
        cwd=".",
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Error:" in result.stderr
    assert "AI_API_KEY" in result.stderr
