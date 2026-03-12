# PRD：NepTune Upwork 招聘线索抓取（当前版本 v1）

本文档根据当前爬虫实现反向整理，描述已上线的产品需求与行为。

---

## 一、产品目标与用户

- **目标**：持续抓取 Upwork 上与「AI 短剧」「漫画/二次元视频」相关的招聘/项目线索，落库并推送到指定 Telegram 群/私聊，供团队跟进。
- **用户**：运营/招聘侧，需要集中查看海外短剧、条漫类外包/全职机会。

---

## 二、功能范围（当前版本）

| 功能 | 说明 |
|------|------|
| 数据源 | 仅 **Upwork**（通过 Apify Actor 抓取，无自建浏览器/RSS）。 |
| 关键词 | 从 `config/keywords.yaml` 的 `upwork.search_queries` 读取，**按条依次搜索**，结果合并去重。 |
| 存储 | SQLite（`data/leads.db`），表名 `leads`，按 `id` 去重（INSERT OR IGNORE）。 |
| 推送 | 可选：抓取结束后将本次新线索推送到 Telegram（群或私聊），卡片格式见下。 |
| 定时 | 可选：通过 `run_scheduler` 在每日指定时间（默认 9:00）执行一次抓取并推送。 |
| 其他平台 | Backstage、LinkedIn 仅占位，执行时提示「未实现」。 |

---

## 三、抓取逻辑（Apify）

- **依赖**：必须在 `.env` 中配置 `APIFY_API_TOKEN`；未配置时跳过 Upwork 抓取并返回 0 条。
- **Actor**：`the-empire-strikes-back/upwork-scraper`（Lite 模式）。
- **调用方式**：Actor 仅接受单条 `searchQuery`（字符串），因此对 `search_queries` 中**每一条关键词**单独发起一次 Run，每次 `maxItems` 上限 20（或与 `max_leads` 取较小值）。
- **筛选条件（或关系）**：满足**任一条**即保留——**时薪 ≥30 USD** 或 **固定价 ≥1000 USD**。因 Actor 同时只能按一种预算类型筛选，对每条关键词会**调用两次**：一次仅传 `hourlyRateMin: 30`，一次仅传 `fixedPriceMin: 1000`，两次结果合并后按 `lead.id` 去重。  
  - **Location**：每次调用均传 `location: ["worldwide", ""]`，用于筛选全球可投或未限制地域的职位（具体是否生效取决于 Actor 是否支持该参数）。
- **流程**：  
  1. 读取关键词列表；  
  2. 对每条关键词先以「时薪≥30」调用 Actor，再以「固定≥1000」调用 Actor，从两次 Run 的 dataset 拉取 items；  
  3. 将每条 item 映射为内部 lead 结构（见下），按 `lead.id` 去重；  
  4. 达到 `max_leads` 后不再请求后续关键词；  
  5. 将去重后的列表写入 SQLite（INSERT OR IGNORE），并返回本次条数及列表供推送使用。

---

## 四、关键词配置（当前 10 条）

- **第一组：核心短剧类（4 条）**  
  AI Short Drama、AI Mini Series、AI Vertical Video、AI Drama Series  
- **第二组：漫画/二次元类（6 条）**  
  AI Manga Video、AI Anime Series、AI Comic Animation、AI Manhwa Video、GenAI Video Animation、AI Webtoon  

配置文件：`config/keywords.yaml` → `upwork.search_queries`。

---

## 五、数据模型

### 5.1 Lead 单条结构（内存/推送用）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | `upwork_{job_id}`，全局唯一 |
| platform | string | 固定 `upwork` |
| source_url | string | 职位详情页 URL |
| title | string | 职位标题 |
| publisher | string | 发布方/客户名（Apify 无时用 "—"） |
| description | string | 职位描述全文（Apify 的 description_text 等） |
| budget_signal | string | 预算展示：时薪与固定价有则都显示，用「时薪 xxx \| 固定 xxx」或单一项 |
| salary_raw | string | 原始预算信息 |
| extra | object | 如 `{ "source": "apify", "work_location": "...", "hourly_range": "$30-50/hr", "fixed_budget": "$1000" }` |
| published_at | string | ISO 或日期字符串 |
| crawled_at | string | 抓取时间 ISO |

### 5.2 存储（SQLite）

- **表名**：`leads`  
- **主键**：`id`  
- **字段**：id, platform, source_url, title, publisher, description, budget_signal, salary_raw, extra_json, published_at, crawled_at  
- **去重**：同一 `id` 仅保留一条（INSERT OR IGNORE）。

---

## 六、Telegram 推送

- **触发**：执行 `python -m src.run upwork`（或 `--platform upwork`）且本次抓取到至少 1 条线索时，若未加 `--no-telegram` 则自动推送。
- **配置**：`.env` 中 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`（可为群组 ID，如 `-5070754724`）。
- **卡片格式**（每条线索一条消息）：
  - 🎯 新线索：[Upwork]
  - 📝 需求标题：{title}
  - 📍 工作地点：{extra.work_location 或 publisher 或 "—"}
  - 💰 预算信号：{budget_signal：时薪与固定价有则都显示，如「时薪 $30-50/hr \| 固定 $1000」或其中一项}
  - 🔍 核心描述：{description 前 30 字}
  - 🔗 直达链接：{source_url}
  - 🕐 发布时间：{published_at 格式化为「X小时前发布」「昨天发布」等}

---

## 七、入口与参数

- **命令**：`python -m src.run [upwork] [选项]` 或 `python -m src.run --platform upwork [选项]`
- **选项**：
  - `--dry-run`：只跑抓取逻辑，不写入 DB、不推送。
  - `--no-telegram`：写入 DB，但不推送 Telegram。
  - `--max-leads N`：本次最多保留 N 条线索（默认 5；0 表示不限制）。

---

## 八、定时任务

- **命令**：`python -m src.run_scheduler`
- **行为**：常驻进程，在每日指定时间（默认 9:00，可由 `TELEGRAM_PUSH_HOUR`、`TELEGRAM_PUSH_MINUTE`、`TZ` 配置）执行一次 `crawl_upwork` 并将新线索推送到 Telegram。

---

## 九、筛选条件汇总

| 条件 | 实现方式 | 说明 |
|------|----------|------|
| 时薪 ≥30 **或** 固定价 ≥1000 | 每条关键词调用 Actor 两次：一次 `hourlyRateMin: 30`，一次 `fixedPriceMin: 1000`，结果合并去重 | 满足任一即保留 |
| Location | 每次调用传 `location: ["worldwide", ""]` | 筛选全球可投/未限制地域（依 Actor 是否支持而定） |
| 推送展示 | `budget_signal` 与 `extra.hourly_range` / `extra.fixed_budget` | 时薪与固定价均在卡片中显示（有则显示，用 \| 分隔） |

---

## 十、配置清单

| 配置项 | 位置 | 必填 | 说明 |
|--------|------|------|------|
| APIFY_API_TOKEN | .env | 是（Upwork） | Apify API 密钥，无则跳过 Upwork |
| TELEGRAM_BOT_TOKEN | .env | 推送时必填 | Telegram Bot Token |
| TELEGRAM_CHAT_ID | .env | 推送时必填 | 接收推送的聊天/群 ID |
| upwork.search_queries | config/keywords.yaml | 是 | 关键词列表，见第四节 |
| base_url 等 | config/sites.yaml | 可选 | Upwork base_url 等，有默认值 |
| DATA_DIR | .env | 否 | 数据目录，默认 ./data |
| TELEGRAM_PUSH_HOUR / MINUTE / TZ | .env | 否 | 定时推送时间与时区 |

---

## 十一、依赖与限制

- **Python**：3.10+
- **外部依赖**：`apify-client`、`pyyaml`、`python-dotenv`；Telegram 推送无需 Playwright。
- **限制**：  
  - Upwork 数据完全依赖 Apify Actor 可用性与配额；  
  - 关键词过多会触发多次 Actor Run，注意 Apify 计费与速率；  
  - 工作地点等字段在 Lite 模式下可能为空，卡片显示为 "—"。

---

## 十二、文档与代码对应

- 抓取逻辑：`src/crawlers/upwork.py`（Apify 调用、lead 映射、入库）
- 推送格式：`src/telegram_notify.py`（format_lead_message、push_leads）
- 存储：`src/storage/store.py`（init_db、insert_leads、get_recent_leads）
- 入口：`src/run.py`、`src/run_scheduler.py`
- 关键词：`config/keywords.yaml`
- 站点配置：`config/sites.yaml`
