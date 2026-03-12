# Upwork 拿不到 RSS 时的替代方案

RSS 或 feed 不可用时，可用以下方式收线索并推送到 Telegram。

---

## 方案一：手动导入链接（已实现，推荐）

不自动抓，你在浏览器里过完真人验证后，把想跟进的职位**详情页链接**复制下来，交给程序入库并推送。

**步骤：**

1. 在浏览器打开 Upwork 搜索，过完 Cloudflare 验证，看到职位列表。
2. 点进感兴趣的职位，复制浏览器地址栏的链接（形如 `https://www.upwork.com/freelance-jobs/apply/xxx_~0220.../`）。
3. 在项目里创建 `data/upwork_links.txt`，**每行贴一个链接**。可选：同一行用 Tab 或逗号分隔「标题,链接」，例如：
   ```
   https://www.upwork.com/freelance-jobs/apply/Video-Creator_~022026170044277888904/
   My Job Title	https://www.upwork.com/freelance-jobs/apply/...
   ```
4. 在项目根目录执行：
   ```bash
   python scripts/import_upwork_links.py
   ```
   默认会导入到 `data/leads.db` 并推送到 Telegram。加 `--no-telegram` 则只导入不推送。
5. 指定其他文件：`python scripts/import_upwork_links.py /path/to/links.txt`

适合：偶尔手动挑几条高意向职位，导入后统一走 Telegram 推送和后续流程。

---

## 方案二：Cookie 复用（需自行配置）

在**自己浏览器**里登录 Upwork 并完成一次真人验证后，把 Cookie 导出给 Playwright 用，有可能在一段时间内不再弹出验证（Cookie 过期后需重新导出）。

**大致步骤：**

1. 用 Chrome 登录 Upwork，手动过完一次 Cloudflare。
2. 安装导出 Cookie 的插件（如 EditThisCookie、Cookie-Editor），或使用开发者工具导出为 JSON。
3. 把 Cookie 存成文件（如 `data/upwork_cookies.json`），格式为 Netscape 或 JSON 数组（名、值、域名、路径等）。
4. 在爬虫里用 Playwright 的 `context.add_cookies(...)` 在打开 Upwork 前注入 Cookie（当前代码未内置，需你自行加几行读取文件并 `add_cookies`）。

注意：Cookie 可能含登录态，不要提交到公开仓库；且 Upwork 可能定期失效，需隔一段时间重新导出。

---

## 方案三：Apify 等云爬虫

用 [Apify Upwork Scraper](https://apify.com/matthewjames/upwork-job-scraper) 等现成 Actor：在 Apify 上配置关键词、跑任务，导出 CSV/JSON。本地再写一个小脚本，**读取导出文件**，解析成和当前 `leads` 表一致的字段，调用现有 `insert_lead` / `push_leads` 入库并推送 Telegram。

优点：反爬、验证由 Apify 处理；缺点：需注册 Apify，可能有免费额度或付费。

---

## 方案四：先做 Backstage / LinkedIn

若 Upwork 暂时难以自动化，可先把 **Backstage**、**LinkedIn** 的抓取或导入做起来，用这两边的线索跑通「入库 → Telegram 推送」流程，Upwork 之后再接 RSS 或 Apify。

---

**建议**：优先用 **方案一（手动导入）**，配合 `data/upwork_links.txt` 与 `scripts/import_upwork_links.py`。当前主流程为 Apify 抓取（见 README），手动导入作为补充。
