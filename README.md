# NepTune Crawler — AI 短剧招聘线索抓取

按日抓取 Upwork（及后续 Backstage、LinkedIn）上与 AI 短剧相关的招聘/项目信息，落库 SQLite，可选 Telegram 推送，并通过 V3 线索网站浏览与跟进。

## 技术方案

见 [docs/TECH_DESIGN.md](docs/TECH_DESIGN.md)。

## 环境

- Python 3.10+
- 建议 venv：`python3 -m venv .venv && source .venv/bin/activate`（Windows 下 `.venv\Scripts\activate`）

## 安装

```bash
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env`，按需填写：

| 变量 | 说明 |
|------|------|
| **APIFY_API_TOKEN** | 必填。Upwork 通过 Apify Actor 抓取，在 [Apify Console](https://console.apify.com/account/integrations) 获取。 |
| **TELEGRAM_BOT_TOKEN** / **TELEGRAM_CHAT_ID** | 可选。推送汇总到 Telegram；未填则从 getUpdates 尝试获取并写回 .env。 |
| **VOLCANO_API_KEY**（或 ARK_API_KEY） | 可选。火山引擎摘要，将职位描述总结为中文；未配置则用描述前 30 字。 |
| **WEB_LOGIN_USER** / **WEB_LOGIN_PASSWORD** / **WEB_SECRET_KEY** | 可选。V3 网站登录，默认 Sylicora / JustGetItDone。 |
| **DATA_DIR** | 可选。默认 `data/`，存 SQLite 与爬取状态。 |

关键词与站点：`config/keywords.yaml`（`upwork.search_queries`）、`config/sites.yaml`。

## 运行

```bash
# 抓取 Upwork，落库 data/leads.db，有 Telegram 配置则推送一条汇总
python -m src.run upwork

# 试跑不落库、不推送
python -m src.run upwork --dry-run

# 抓取但不推送到 Telegram
python -m src.run upwork --no-telegram

# 清空历史后重新抓取（首次 100 条）
python -m src.run upwork --clear
```

**定时抓取**：用 crontab 或 systemd timer 每天执行一次，例如：

```bash
0 9 * * * cd /path/to/crawler && .venv/bin/python -m src.run upwork >> logs/cron.log 2>&1
```

或常驻调度器（默认每天 9:00）：

```bash
python -m src.run_scheduler
```

详见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## V3 线索网站（CRM）

在项目根目录启动：

```bash
python -m src.web.app
```

默认 <http://127.0.0.1:5050>（可用 `PORT` 修改）。登录后：线索总览（分页、按时间/状态/关键词筛选）、待处理/跟进中/已转化/已忽略、详情页（火山中文总结为「完整描述」）、状态与备注跟进。数据来源为同一 `data/leads.db`。

## 数据

- SQLite：`data/leads.db`（表结构见 [TECH_DESIGN](docs/TECH_DESIGN.md) 第六节）。
- 可通过 `DATA_DIR` 指定目录。

## 当前实现

- **Upwork**：Apify Actor（the-empire-strikes-back/upwork-scraper），按关键词搜索、合并去重、首次 100 条/之后增量，写入 `leads` 表。见 [docs/PRD/PRD-Upwork-Crawler-v1.md](docs/PRD/PRD-Upwork-Crawler-v1.md)、[v2 摘要](docs/PRD/PRD-Upwork-Crawler-v2.md)。
- **Telegram**：推送一条汇总（完成时间、线索数量、soraplayground.com 链接）。
- **V3 网站**：见 [docs/PRD/PRD-V3-Leads-Website-CRM.md](docs/PRD/PRD-V3-Leads-Website-CRM.md)。
- Backstage、LinkedIn 未实现；`--platform backstage/linkedin` 会提示未实现。

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/TECH_DESIGN.md](docs/TECH_DESIGN.md) | 技术方案与数据模型 |
| [docs/DEPLOY.md](docs/DEPLOY.md) | 服务器部署与定时任务 |
| [docs/PRD/](docs/PRD/) | Upwork v1/v2、V3 线索网站 PRD |
| [docs/ALTERNATIVES.md](docs/ALTERNATIVES.md) | Upwork 无 RSS 时的替代方案 |
| [docs/CRAWL_STRATEGY.md](docs/CRAWL_STRATEGY.md) | 爬取策略说明 |

## 注意

- 每日执行一次即可，请勿高频请求；关键词条数会影响 Apify 调用与计费。
- 抓取行为可能违反平台 ToS，请自行评估合规与风险。
