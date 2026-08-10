from pathlib import Path


def test_daily_workflow_keeps_github_cron_backup_and_local_push_trigger():
    workflow = Path(".github/workflows/daily-ai-news.yml").read_text(encoding="utf-8")

    assert "push:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert 'cron: "17 11 * * *"' in workflow
    assert 'cron: "47 11 * * *"' in workflow
    assert 'cron: "17 12 * * *"' in workflow
    assert 'cron: "45 12 * * *"' in workflow
    assert 'cron: "15 13 * * *"' in workflow
    assert 'cron: "45 13 * * *"' in workflow


def test_daily_workflow_can_be_smoke_tested_by_workflow_push():
    workflow = Path(".github/workflows/daily-ai-news.yml").read_text(encoding="utf-8")

    assert "push:" in workflow
    assert "branches:" in workflow
    assert "- main" in workflow
    assert "paths:" in workflow
    assert "- .github/workflows/daily-ai-news.yml" in workflow
    assert "- .github/automation-trigger.txt" in workflow
    assert "workflow_dispatch:" in workflow
    assert "report_date:" in workflow


def test_daily_workflow_can_dry_run_without_sending_or_marking_email():
    workflow = Path(".github/workflows/daily-ai-news.yml").read_text(encoding="utf-8")

    assert "dry_run:" in workflow
    assert "DRY_RUN: ${{ inputs.dry_run || 'false' }}" in workflow
    assert "inputs.dry_run != true" in workflow
    assert "name: Mark email sent" in workflow
    assert "name: Commit report" in workflow


def test_daily_workflow_skips_only_after_email_sent_marker_exists():
    workflow = Path(".github/workflows/daily-ai-news.yml").read_text(encoding="utf-8")

    assert "id: email_marker" in workflow
    assert 'TZ=Asia/Shanghai date +%F' in workflow
    assert 'reports/.email-sent-${report_date}' in workflow
    assert 'if: github.event_name == \'workflow_dispatch\' || steps.email_marker.outputs.exists != \'true\'' in workflow
    assert "Generate and email daily report" in workflow
    assert "Mark email sent" in workflow
    assert "reports/.email-sent-*" in workflow


def test_local_trigger_script_commits_trigger_file_for_push_workflow():
    script = Path("scripts/trigger-daily-ai-news.ps1").read_text(encoding="utf-8")

    assert '[string]$RepoPath = "E:\\AI-news"' in script
    assert ".github/automation-trigger.txt" in script
    assert "Invoke-Git fetch origin main:refs/remotes/origin/main" in script
    assert "Invoke-Git rebase origin/main" in script
    assert "Invoke-Git" in script
    assert "throw \"git" in script
    assert "exit $LASTEXITCODE" not in script
    assert 'REPORT_DATE=' in script
    assert "UTF8Encoding($false)" in script
    assert "Set-Content" not in script
    assert "Invoke-Git add .github/automation-trigger.txt" in script
    assert "Invoke-Git commit -m \"ci: trigger daily ai news\"" in script
    assert "Invoke-Git push origin main" in script
    assert "Invoke-WorkflowDispatch" in script
    assert "git trigger failed; dispatched workflow through GitHub API" in script
    assert "exit 0" in script
    assert "actions/workflows/daily-ai-news.yml/dispatches" in script
    assert "report_date = $ReportDate" in script


def test_committed_trigger_file_contains_report_date_for_workflow_push():
    trigger = Path(".github/automation-trigger.txt").read_text(encoding="utf-8-sig")

    assert "REPORT_DATE=" in trigger
    assert "TRIGGERED_AT=" in trigger


def test_daily_workflow_syncs_before_pushing_reports():
    workflow = Path(".github/workflows/daily-ai-news.yml").read_text(encoding="utf-8")

    assert "concurrency:" in workflow
    assert "fetch-depth: 0" in workflow
    assert "git fetch origin main:refs/remotes/origin/main" in workflow
    assert "git rebase origin/main" in workflow
    assert "git push origin HEAD:main" in workflow
    assert "git push\n" not in workflow


def test_daily_workflow_uses_zhipu_free_default():
    workflow = Path(".github/workflows/daily-ai-news.yml").read_text(encoding="utf-8")

    assert "models: read" not in workflow
    assert "AI_API_KEY: ${{ secrets.ZHIPU_API_KEY || secrets.AI_API_KEY }}" in workflow
    assert "AI_BASE_URL: https://open.bigmodel.cn/api/paas/v4" in workflow
    assert "AI_MODEL: glm-4.7-flash" in workflow
    assert "AI_API_STYLE: chat_completions" in workflow


def test_daily_workflow_uses_node_24_compatible_actions():
    workflow = Path(".github/workflows/daily-ai-news.yml").read_text(encoding="utf-8")

    assert "uses: actions/checkout@v6" in workflow
    assert "uses: actions/setup-python@v6" in workflow
    assert "uses: actions/checkout@v4" not in workflow
    assert "uses: actions/setup-python@v5" not in workflow


def test_daily_workflow_uses_trigger_report_date_to_avoid_midnight_queue_drift():
    workflow = Path(".github/workflows/daily-ai-news.yml").read_text(encoding="utf-8")

    assert "id: trigger_context" in workflow
    assert 'grep -E "^REPORT_DATE="' in workflow
    assert "sed 's/^\\xEF\\xBB\\xBF//'" in workflow
    assert '[ "${{ github.event_name }}" = "workflow_dispatch" ]' in workflow
    assert "${{ inputs.report_date }}" in workflow
    assert '[ "${{ github.event_name }}" = "schedule" ]' in workflow
    assert "date -u +%F" in workflow
    assert "steps.trigger_context.outputs.report_date" in workflow
    assert "python -m ai_news.main --report-date" in workflow
    assert "reports/.email-sent-${report_date}" in workflow
