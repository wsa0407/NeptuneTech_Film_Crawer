# AI 短剧招聘线索抓取系统 — 技术方案设计

> 本文档为初期技术方案；当前实现已包含 Telegram 推送、火山引擎摘要与 V3 线索网站（CRM），详见 [README](../README.md) 与 [docs/PRD](PRD/)。

## 一、需求约束（已确认）

| 项 | 决定 |
|----|------|
| 监控频率 | 每天执行一次 |
| 优先级 | 暂不实现优先级标记 |
| Telegram 推送 | 已实现：汇总一条（完成时间、线索数、链接） |
| 薪资 | 保留网站原文，不做解析或归一化 |
| 关键词 | 采用下文「统一关键词表」 |

---

## 二、统一关键词表

用于各平台搜索/过滤的标准化关键词（含你补充项）：

**短剧 / 形态**
- Short Drama / Short-form Drama / Micro-drama
- Vertical Drama
- Mini-series
- ShortMax, DramaBox（剧集/平台名）

**AI / AIGC**
- AI / AIGC / Synthetic
- AI-generated footage
- AIGC integration
- Generative AI Video
- AI-native
- Character Consistency（技术向）

**角色与岗位**
- AIGC Video Creator / Producer
- Short-form Video Producer
- Creative Editor
- Head of Content
- Content Acquisition

**检索时可组合**：例如 `(Vertical Drama OR Short Drama OR Short-form Drama OR Micro-drama) AND (AI OR AIGC OR Generative AI Video OR …)`，具体组合按各平台搜索能力在实现时定。

---

## 三、系统架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Scheduler (每日 1 次)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Upwork Crawler │ │ Backstage       │ │ LinkedIn        │
│                 │ │ Crawler         │ │ Crawler         │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
                  ┌─────────────────────┐
                  │  Dedup & Normalize  │
                  │  (可选，24h 去重)   │
                  └──────────┬──────────┘
                             ▼
                  ┌─────────────────────┐
                  │  Storage (SQLite/   │
                  │  JSON/DB)           │
                  └─────────────────────┘
```

- **调度**：每日跑一次（具体时间可配置，如凌晨）。
- **三个爬虫**：Upwork、Backstage、LinkedIn 各自独立模块，可单独跑、单独重试。
- **去重**（可选）：若后续要接 Telegram，可在此做 24h 内跨平台去重；本期可只做单平台去重或不做。
- **存储**：先本地文件或 SQLite，便于后续加 API / Telegram。

---

## 四、技术栈建议

| 层次 | 选型 | 说明 |
|------|------|------|
| 语言 | Python 3.10+ | 生态成熟，爬虫、调度、数据处理库多 |
| 爬虫 / 页面 | Playwright 或 Puppeteer (Node) | 若选 Python：Playwright；若选 Node：Puppeteer。需 JS 渲染时用；若某站有 RSS/简单 HTML，可用 requests + BeautifulSoup |
| 请求 | httpx / requests | 非 JS 页面用；配合 retry、timeout、简单限速 |
| 调度 | cron（系统）或 APScheduler（Python） | 每日一次用 cron 最简；若希望进程内调度用 APScheduler |
| 存储 | SQLite + 可选 JSON 导出 | 单机、无运维；表结构见下 |
| 代理 | 环境变量配置，可选 | 仅 LinkedIn 建议代理；Upwork/Backstage 视情况 |
| 配置 | .env + 单 YAML/JSON | 关键词、目标 URL、间隔、开关等 |

不优先引入：消息队列、Redis、大型数据库（除非你已有）。

---

## 五、各平台抓取设计

### 5.1 Upwork

- **目标**：高预算、支付已验证的 AI 短剧/视频类项目。
- **入口**：  
  - 优先确认是否仍有 **RSS**（若有，用 RSS 做每日拉取，再过滤）。  
  - 若无 RSS 或字段不足：用 **搜索页 URL**，把关键词编码进 query（Upwork 实际支持的语法需实现时查一次）。
- **过滤（在拿到数据后做）**  
  - Payment Verified：仅保留“支付已验证”。  
  - Spend > $10k：若有该字段则优先标记或单独列表；若无则忽略。  
- **抓取字段**：项目标题、详细描述、预算金额（原文）、雇主评价等级、发布时间、雇主名称、项目 URL。  
- **频率与限速**：每日 1 次；请求间隔 5–15 秒随机延迟，避免被封。  
- **技术实现**：  
  - 若 RSS 可用：定时请求 RSS URL，解析 XML，映射到统一数据模型。  
  - 若用网页：Playwright 打开搜索页，解析列表（+ 可选详情页），再写入存储。  
- **合规**：需知悉 Upwork ToS；建议用单账号、低频率、仅读公开列表。

### 5.2 Backstage

- **目标**：Casting Calls 中与短剧 / AI 相关的招募公告，识别有预算的制片方。
- **入口**：Backstage 官网 **Casting Calls** 栏目固定 URL（实现时在配置里写死或可配）。
- **关键词**：ShortMax, DramaBox, Vertical Drama, Mini-series, Short-form Drama, Micro-drama, AIGC, AI 等（从统一关键词表取子集，适合 Casting 场景）。
- **抓取字段**：剧组名称、制片方/实体、拍摄地点、薪资/报酬（**网站原文整段或整句，不做解析**）、申请链接、公告标题、URL、发布时间。
- **频率与限速**：每日 1 次；请求间隔 5–15 秒随机延迟。
- **实现**：请求 Casting Calls 列表页（若需 JS 则 Playwright），解析列表项，必要时进详情页取“薪资”等长文本，原样写入“薪资原文”字段。

### 5.3 LinkedIn

- **目标**：目标公司的 Jobs 发布；可选：高管/决策者动态（若做，需单独评估合规与可行性）。
- **范围**：  
  - 公司列表示例：Crazy Maple Studio (ReelShort), StoryMatrix (DramaBox), Jiuzhou Culture (ShortMax) 等（列表放配置）。
  - 职位描述关键词：AI-generated footage, AIGC integration, Creative Editor, AIGC Video Creator/Producer, Short-form Video Producer, Generative AI Video 等（从统一关键词表取）。
- **抓取字段**：公司名、职位标题、职位描述、职位 URL、发布时间、薪资（若有且为原文则原样保存）。
- **频率与限速**：每日 1 次；单账号日请求量严格控制（如 20 条/天）；多账号轮换时总配额分配见下。
- **实现建议**：  
  - **Jobs**：若 LinkedIn 提供公司 Jobs 的公开 URL，优先用该 URL 列表 + 请求/Playwright 抓取；否则用搜索页 + 公司名过滤。  
  - **代理**：建议住宅代理（美国/东南亚），降低数据中心 IP 风控。  
  - **行为**：随机延迟 5–15 秒、模拟滚动、控制每日总量。  
- **高管动态**：PRD 中“Boolean 搜索 + 主页动态”本期可**不实现**，或仅做需求与合规预留；若以后做，需单独设计（登录策略、ToS、配额）。
- **账号**：多账号轮换时，明确“20/天”是“每账号 20 条 Job 或 20 个 Profile”，并在设计里写清，避免超限。

---

## 六、数据模型（存储）

统一一条“线索”为一条记录，各平台字段映射到同一张表或同一 JSON 结构，便于以后去重、导出和接 Telegram。

**建议表结构（SQLite）**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 全局唯一，如 uuid 或 `{platform}_{platform_id}` |
| platform | TEXT | upwork / backstage / linkedin |
| source_url | TEXT | 线索详情页 URL |
| title | TEXT | 职位/项目/公告标题 |
| publisher | TEXT | 雇主名/公司名/制片方 |
| description | TEXT | 核心描述或摘要（可截断） |
| budget_signal | TEXT | 预算/金额相关原文（Upwork）；Backstage 可为空或与 salary 合并 |
| salary_raw | TEXT | 薪资原文（仅 Backstage/LinkedIn 有则填，**不解析**） |
| extra_json | TEXT | 其他字段（如雇主评分、地点、申请链接等）JSON |
| published_at | TEXT | 发布时间（ISO8601 或平台原文） |
| crawled_at | TEXT | 抓取时间 ISO8601 |

**去重**：  
- 同一 `source_url` 或同一 `id` 视为同一条；若 24h 内已存在则不再插入（可选）。  
- 跨平台去重本期可不做，或仅用 `title + publisher` 简单相似度（后续再细化）。

---

## 七、项目结构建议

```
crawler/
├── config/
│   ├── keywords.yaml      # 统一关键词表
│   └── sites.yaml         # 各站 URL、选择器、公司列表等
├── src/
│   ├── crawlers/
│   │   ├── base.py        # 公共基类（请求、延迟、重试）
│   │   ├── upwork.py
│   │   ├── backstage.py
│   │   └── linkedin.py
│   ├── storage/
│   │   └── store.py       # 写入 SQLite / JSON
│   ├── dedup.py           # 可选 24h 去重
│   └── run.py             # 入口：按配置跑各 crawler
├── data/                  # SQLite 文件或 JSON 输出目录
├── .env.example
├── requirements.txt
└── README.md
```

- **config**：关键词与站点配置与代码分离，便于你增删关键词和 URL。  
- **crawlers**：各平台一个模块，base 里统一延迟、User-Agent、重试。  
- **storage**：统一写入接口，便于以后换 DB 或加 API。  
- **run.py**：支持 `--platform upwork|backstage|linkedin|all` 和 `--dry-run`，方便调试和 cron 调用。

---

## 八、调度与运行方式

- **每日一次**：用系统 cron 或 APScheduler 在固定时间（如 02:00）执行一次。  
- **命令示例**：`python src/run.py --platform all` 或分别 `--platform upwork` 等。  
- **日志**：输出到文件 + 控制台，包含每平台成功/失败条数、错误摘要，便于排查。

---

## 九、安全与合规要点

- **不抓取**：登录后私有聊天、非公开动态、受隐私保护的个人联系方式（若招聘页带邮箱/电话，是否允许存“原文”需你合规确认）。  
- **限速与量**：严格按每日一次、每站随机延迟、LinkedIn 单账号日上限执行。  
- **配置**：代理、账号等放 .env，不提交到代码库。  
- **ToS**：各平台抓取前需知悉并接受其使用条款与封禁风险。

---

## 十、本期不做（预留）

- 优先级标记（High Priority 等）。  
- 薪资解析与归一化（仅存原文）。  
- LinkedIn 高管动态抓取（可后续单独评估）。  
- 跨平台 24h 去重（可选做简单版）。

---

## 十一、实现顺序建议

1. **基础框架**：项目结构、config、base crawler、SQLite 存储、`run.py`。  
2. **Upwork**：RSS 或搜索页抓取 + 字段映射 + 过滤（Payment Verified，Spend 若有）。  
3. **Backstage**：Casting Calls 列表 + 详情，薪资原文写入。  
4. **LinkedIn**：公司 Jobs 列表 + 关键词过滤，配额与延迟。  
5. **去重与导出**：可选 24h 去重、JSON/CSV 导出，便于后续接 Telegram 或报表。

如果你认可这份技术方案，我可以下一步按该设计在仓库里搭好基础框架和配置文件（仍不实现具体爬虫逻辑，或只实现一个平台示例）。你可以告诉我：希望用 Python 还是 Node，以及是否先做 Upwork/Backstage/LinkedIn 中的哪一个。
