# AI-news

`AI-news` 是一个每日自动化脚本项目：它会抓取最新 AI 热点新闻，调用 AI 模型生成中文 Markdown 简报，然后发送到你的个人邮箱，并把每日报告保存到 GitHub 仓库。

这个项目面向 AI 训练师初学者。你不需要先成为程序员，也可以通过它理解新闻抓取、提示词、模型总结、邮件发送和自动化任务这些基础流程。

## 每天会发生什么

北京时间每天 19:00，GitHub Actions 会自动运行：

1. 抓取 AI 新闻候选。
2. 去重、筛选最近 24-48 小时的重要内容。
3. 如果新闻太少，扩展到最近 72 小时。
4. 调用你配置的 AI 模型生成 Markdown 简报。
5. 把简报转成 HTML 邮件发给你。
6. 保存 `reports/YYYY-MM-DD.md`。
7. 自动提交报告到仓库。

## 简报内容

每封邮件包含：

- 今日速览
- 8-10 条重点新闻
- 每条新闻的“发生了什么”“为什么重要”“初学者学习提示”
- 今日概念补充
- AI 训练师学习向代码示例
- 原始链接列表

## 需要配置的 GitHub Secrets

进入 GitHub 仓库：

`Settings -> Secrets and variables -> Actions -> New repository secret`

添加这些值：

| Secret | 是否必填 | 说明 |
| --- | --- | --- |
| `GEMINI_API_KEY` | 推荐必填 | Gemini API Key，GitHub Actions 会优先使用它 |
| `AI_API_KEY` | 兼容备用 | 没有 `GEMINI_API_KEY` 时才使用这个通用模型 Key |
| `AI_BASE_URL` | 本地运行可填 | AI 接口地址；GitHub Actions 默认使用 Gemini |
| `AI_MODEL` | 本地运行可填 | 模型名称；GitHub Actions 默认使用 `gemini-3.6-flash` |
| `AI_API_STYLE` | 本地运行可填 | Gemini 使用 `chat_completions` |
| `MAIL_HOST` | 建议填写 | 网易邮箱填 `smtp.163.com` |
| `MAIL_PORT` | 建议填写 | 网易邮箱 SSL 端口填 `465` |
| `MAIL_USERNAME` | 必填 | 发件网易邮箱 |
| `MAIL_PASSWORD` | 必填 | 网易邮箱 SMTP 授权码，不是登录密码 |
| `MAIL_FROM` | 必填 | 发件邮箱 |
| `MAIL_TO` | 必填 | 收件邮箱，可以和发件邮箱相同 |
| `NEWS_API_PROVIDER` | 可选 | 例如 `newsapi` |
| `NEWS_API_KEY` | 可选 | 新闻搜索 API Key |

不要把 API Key、邮箱授权码写进代码，也不要提交到仓库。只放在 GitHub Secrets 或本地 `.env` 文件里。

## AI_BASE_URL 是什么

`AI_BASE_URL` 是程序调用模型的接口地址，不是浏览器里的后台页面。

GitHub Actions 现在默认使用 Gemini 免费模型：

```text
AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
AI_MODEL=gemini-3.6-flash
AI_API_STYLE=chat_completions
```

其他兼容接口例子：

```text
https://api.openai.com/v1
https://api.deepseek.com/v1
https://api.aicodemirror.com/api/codex/backend-api/codex
```

如果你使用 AICodeMirror，并且它给你的 Codex 接口是：

```text
https://api.aicodemirror.com/api/codex/backend-api/codex
```

可以先把它填到 `AI_BASE_URL`，并把 `AI_API_STYLE` 设置为：

```text
responses
```

## 网易邮箱授权码

网易邮箱发信通常不能直接使用登录密码。你需要在网易邮箱设置里开启 SMTP，并生成“授权码”。

把授权码填入：

```text
MAIL_PASSWORD
```

如果邮件发送失败，优先检查：

- `MAIL_HOST` 是否是 `smtp.163.com`
- `MAIL_PORT` 是否是 `465`
- `MAIL_PASSWORD` 是否是 SMTP 授权码
- `MAIL_TO` 是否填写正确

## 手动运行 GitHub Actions

你可以不等到每天 19:00，手动测试一次：

1. 打开 GitHub 仓库页面。
2. 点击 `Actions`。
3. 选择 `Daily AI News`。
4. 点击 `Run workflow`。
5. 等待运行完成，查看日志、邮箱和 `reports/` 目录。

## 本地测试

安装依赖：

```bash
python -m pip install -e ".[dev]"
```

运行测试：

```bash
pytest -v
```

只生成 Markdown，不发送邮件：

```powershell
$env:DRY_RUN="true"
python -m ai_news.main --dry-run
```

如果 Windows 上 `python` 不可用，可以尝试：

```powershell
py -3.11 -m pytest -v
```

## 项目结构

```text
src/ai_news/config.py        读取配置
src/ai_news/news_sources.py  抓取、去重、筛选新闻
src/ai_news/summarizer.py    调用 AI 模型生成 Markdown
src/ai_news/email_sender.py  转换 HTML 并发送邮件
src/ai_news/report_store.py  保存 reports/YYYY-MM-DD.md
src/ai_news/main.py          串起完整流程
.github/workflows/           GitHub Actions 定时任务
reports/                     每日 Markdown 简报
```

## 如何修改

- 修改收件人：改 GitHub Secret `MAIL_TO`
- 修改发送时间：改 `.github/workflows/daily-ai-news.yml` 里的 cron
- 修改模型：改 `AI_MODEL`
- 修改模型接口：改 `AI_BASE_URL`
- 添加新闻源：编辑 `src/ai_news/news_sources.py` 里的 `DEFAULT_RSS_FEEDS`
- 启用新闻搜索 API：设置 `NEWS_API_PROVIDER=newsapi` 和 `NEWS_API_KEY`

## 给 AI 训练师初学者的学习建议

每天阅读报告时，可以重点看三件事：

1. 这条新闻改变了什么？
2. 它和提示词、数据标注、模型评估或安全有什么关系？
3. 如果我是 AI 训练师，我能从中学到哪个可操作的方法？

你也可以把“代码示例”当成小练习。例如看到数据标注相关新闻时，可以关注类似结构：

```python
sample = {
    "input": "用户问题",
    "expected_behavior": "模型应该如何回答",
    "risk_label": "低风险/中风险/高风险",
    "review_note": "人工标注员的判断依据",
}
```

这个项目的重点不是只看新闻，而是每天建立一点 AI 训练师需要的判断框架。
