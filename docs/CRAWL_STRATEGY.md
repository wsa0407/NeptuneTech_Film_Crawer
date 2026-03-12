# Upwork 抓取策略说明

> 当前 Upwork 实现采用 **Apify Actor**（`src/crawlers/upwork.py`）。
>
> - **运行/调用方式**：以 README 和 `src/run.py --help` 为准
> - **爬虫内部逻辑**：见 [docs/CRAWLER_LOGIC_UPWORK.md](CRAWLER_LOGIC_UPWORK.md)
>
> 下文保留为「列表页 + 详情页直连」的备用/历史策略说明（供排查或回退参考）。

## 一、当前流程（列表页 ID 提取 + 详情页直连）

因 Upwork RSS 已于 2024 年底下线，采用「列表页只提 ID → 直连详情页」策略，避免点击弹窗导致加载失败。

1. **入口 URL**：`https://www.upwork.com/nx/search/jobs/?q=<关键词>&sort=recency`（关键词来自 `config/keywords.yaml` 的 `upwork.search_queries`）。
2. **列表页**：
   - 等待 `[data-test="job-tile"]` 出现（任务卡片）。
   - 对每个卡片取内部 `a[href*='/jobs/']` 的 href，从中解析出含 `~022027698...` 的 **Job ID**，去重得到本页 ID 列表。
3. **详情页直连**：对每个 Job ID 不点弹窗，直接打开 `https://www.upwork.com/nx/search/jobs/details/~{Job_ID}`。
4. **详情页字段（CSS Selectors）**：
   - **岗位标题**：`h1` 或 `[data-test="job-details-header"] h1`
   - **发布时间**：`span[data-test="posted-on"]`
   - **岗位需求 (Summary)**：`.job-description` 容器内全部文本（含 Responsibilities、Summary 等）
   - **薪水范畴**：`ul.job-info-list` — 若为 Fixed-price 提取金额（如 $800），若为 Hourly 提取薪资范围
5. **去重与上限**：同一 job_id 只保留一条；达到 `--max-leads` 后停止；详情页之间随机延迟（见 `detail_delay_min/max`）。

## 二、配置要点（config/sites.yaml）

- **list_item_selector**：列表页任务卡片，默认 `[data-test='job-tile']`。
- **detail_selectors**：详情页各字段选择器（title、posted_on、description、job_info_list）。
- **detail_delay_min / detail_delay_max**：详情页之间的随机延迟（秒），降低风控。

## 三、为什么可能抓到 0 条

| 原因 | 说明 |
|------|------|
| **页面加载超时** | 列表页或详情页在设定时间内未出现目标选择器（网络、反爬、改版）。 |
| **Cloudflare 真人验证** | 未登录或 headless 时经常出现验证页，列表/详情不渲染。可试非 headless 或手动导入链接。 |
| **选择器改版** | Upwork 调整 `data-test` 或 class 后需同步更新 `sites.yaml` 中的 `list_item_selector` 与 `detail_selectors`。 |

## 四、替代方案（无浏览器 / 免验证）

- **手动导入**：浏览器里过完验证后复制职位详情页链接到 `data/upwork_links.txt`，运行 `python scripts/import_upwork_links.py` 入库并推送。见 `docs/ALTERNATIVES.md`。
- **RSS**：已下线，仅保留兼容；若曾配置 `rss_feed_urls` 仍会尝试拉取。

## 五、建议排查顺序

1. 看 log 是否出现 `List page '...': extracted N job IDs`（N>0 表示列表解析成功）。
2. 若 N>0 但最终 0 条，多为详情页加载失败或选择器不匹配；可加大 `timeout_ms`、核对详情页 DOM 与 `detail_selectors`。
3. 若一直 `extracted 0 job IDs`，检查列表页是否被 Cloudflare 拦截或 `list_item_selector` 是否仍匹配当前页面。
