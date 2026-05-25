# Upwork 爬虫逻辑（Apify Actor：`YdYsB7rsRY0EUb1lP`）

本文档只描述 **Upwork 爬虫内部逻辑**（输入参数、过滤规则、字段映射、数据流）。  
如何运行/调用请看主文档（README）或 `src/run.py --help`。

## 1. 总览

- **入口函数**：`src/crawlers/upwork.py` → `crawl_upwork(from_date, to_date, dry_run=False, max_leads=None)`
- **Actor**：`YdYsB7rsRY0EUb1lP`
- **认证**：`.env` → `APIFY_API_TOKEN`
- **本次抓取范围**：由调用方传入 `from_date` / `to_date`（每次运行前手动指定）
- **关键词规则**：`AI-Generated Video` 只 **匹配 Skills**（不匹配标题/描述）
- **预算规则**：**时薪 ≥ 30** 或 **固定价 ≥ 1000**
- **去重**：按 `lead["id"]`（`upwork_{Uid}`）去重

## 2. Actor 输入（run_input）

由 `_build_run_input(from_date, to_date, limit)` 构建，关键字段如下：

- **条数**：`limit`（当前为 3000）
- **发布时间**：`fromDate` / `toDate`
- **关键词（只匹配技能）**
  - `includeKeywords.keywords = ["AI-Generated Video"]`
  - `includeKeywords.matchSkills = True`
  - `includeKeywords.matchTitle = False`
  - `includeKeywords.matchDescription = False`
- **预算**
  - `budget.allowUnspecifiedBudget = False`
  - `budget.hourlyRate.min = "30"`
  - `budget.fixedPrice.min = "1000"`

其余 `client.* / vendor.* / addons.* / notifications.*` 目前保持默认值（见 `_build_run_input`）。

## 3. 运行流程

1. **准备**：
   - 读取 `APIFY_API_TOKEN`，缺失则直接返回 0 条
   - `limit` 设为 **3000**
   - 读取 `config/sites.yaml` 的 `upwork.base_url`（默认 `https://www.upwork.com`），用于补全详情链接
2. **调用 Actor**：
   - `client.actor(APIFY_ACTOR_ID).call(run_input=run_input)`
   - 从 `run["defaultDatasetId"]` 获取 dataset
3. **遍历结果**：
   - `for item in dataset.iterate_items():`
   - 对每条 `item`：
     - `_meets_budget_filter(item)`：本地预算二次校验（时薪≥30 或 固定≥1000）
     - `_lead_from_apify_item(item, base_url)`：映射为统一 lead 结构
     - `seen` 去重：同一 `lead["id"]` 只保留一条
4. **返回**：
   - `dry_run=True`：只返回列表，不落库
   - 否则：返回列表，落库由上层 `src/run.py` 完成

## 4. 字段映射（item → lead）

转换函数：`_lead_from_apify_item(item, base_url)`，核心字段如下：

- **id**：`upwork_{Uid}`
  - 优先使用 Actor 返回的 `Uid/uid`；缺失时回退到 `job_id/jobId` → URL 中解析 → `id` → URL hash
- **title**：`title/jobTitle/name`
- **description**：`description_text/descriptionText/description/snippet/body`
  - 经过 `_strip_html(..., preserve_newlines=True)` 清洗：去 HTML 标签、保留换行、折叠多余空格
- **source_url**：`url/jobUrl/link`，若缺失则回退到 `/nx/search/jobs/details/~{Uid}`
- **published_at**：`publish_time/postedOn/publishedAt/createdAt/posted_at`（尽量保留原始字符串）
- **budget_signal / salary_raw**：
  - 时薪：`budget_hourly_min_usd/budgetHourlyMinUsd`、`budget_hourly_max_usd/budgetHourlyMaxUsd`
  - 固定价：`budget_total_usd/budgetTotalUsd/fixedPrice`
  - 组装展示字符串：`"时薪 $x-$y/hr | 固定 $z"`（按存在字段拼接）
- **extra**：保存补充信息（如 `work_location`、`hourly_range`、`fixed_budget`）

> 说明：item 字段命名可能存在 snake_case/camelCase 差异，当前转换函数做了兼容回退；如后续发现新字段名，请以真实 item 为准补齐映射。

## 5. 预算二次校验（本地）

函数：`_meets_budget_filter(item)`

- 若 `hourly_min >= 30` → 通过
- 若 `fixed_total >= 1200` → 通过
- 若两类预算字段都不存在 → 通过（信任 Actor 已做预算筛选）
- 否则不通过

## 6. 与上层调用的边界

Upwork 爬虫本身只负责 **抓取并返回 leads**；以下由 `src/run.py` 负责：

- 是否清空数据库（`--clear`）
- 是否做中文摘要（`enrich_leads_with_summary`）
- 落库（`insert_leads`）
- 更新 `last_crawl_at`（仍会写入，但不用于本爬虫的日期范围）
- Telegram 推送

