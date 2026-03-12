# 服务器部署指南

将 NepTune 线索网站部署到服务器，部署后立即爬取 100 条，之后每天早上 9 点自动爬取一次。

---

## 一、服务器准备

### 1. 环境要求

- Linux（如 Ubuntu 22.04）
- Python 3.10+
- 已配置 `.env`（见项目根目录 `.env.example`）：
  - `APIFY_API_TOKEN`（必填，Upwork 爬取）
  - `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`（可选，推送汇总到 Telegram）
  - `WEB_LOGIN_USER`、`WEB_LOGIN_PASSWORD`、`WEB_SECRET_KEY`（可选，网站登录与密钥）
  - `DATA_DIR`（可选，默认 `项目根/data`，存 SQLite 与爬取状态）

### 2. 上传代码并安装依赖

```bash
# 在服务器上进入项目根目录（crawler/）
cd /path/to/crawler

python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

---

## 二、部署网页（Flask + Gunicorn）

### 1. 前台试跑（确认无误后再用 systemd）

```bash
cd /path/to/crawler
source .venv/bin/activate
export PORT=5050
gunicorn -w 2 -b 0.0.0.0:5050 "src.web.app:app"
```

浏览器访问 `http://服务器IP:5050`，能打开登录页即可。

### 2. 用 systemd 常驻运行（推荐）

创建服务文件（如 `/etc/systemd/system/neptune-web.service`）：

```ini
[Unit]
Description=NepTune 线索网站
After=network.target

[Service]
Type=simple
User=你的用户名
WorkingDirectory=/path/to/crawler
Environment=PATH=/path/to/crawler/.venv/bin
Environment=PORT=5050
ExecStart=/path/to/crawler/.venv/bin/gunicorn -w 2 -b 0.0.0.0:5050 "src.web.app:app"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable neptune-web
sudo systemctl start neptune-web
sudo systemctl status neptune-web
```

如需对外 80/443，可在前面加 Nginx 反代（见下文「可选：Nginx 反代」）。

---

## 三、部署后立即爬取 100 条

部署完成后执行一次爬取，**首次**会自动爬 100 条并写入数据库，同时记录「上次爬取时间」供后续增量使用。

在项目根目录、激活虚拟环境后执行：

```bash
cd /path/to/crawler
source .venv/bin/activate
python -m src.run upwork
```

- 若希望**清空历史、从零开始**再爬 100 条，则执行：  
  `python -m src.run upwork --clear`
- 有 Telegram 配置时会推送一条汇总（完成时间、线索数量、soraplayground.com 链接）。

---

## 四、每天早上 9 点爬取一次

任选其一即可。

### 方式 A：crontab（推荐，简单）

```bash
crontab -e
```

加入一行（请把 `/path/to/crawler` 换成实际路径）：

```cron
0 9 * * * cd /path/to/crawler && .venv/bin/python -m src.run upwork >> /path/to/crawler/logs/cron.log 2>&1
```

即每天 9:00 执行一次爬取。若希望用服务器本地时区，可先设置 `TZ`，例如（东八区）：

```cron
0 9 * * * TZ=Asia/Shanghai cd /path/to/crawler && .venv/bin/python -m src.run upwork >> /path/to/crawler/logs/cron.log 2>&1
```

建议先建日志目录：`mkdir -p /path/to/crawler/logs`。

### 方式 B：systemd 定时器（与 cron 二选一）

1. 写爬虫 oneshot 服务，例如 `/etc/systemd/system/neptune-crawl.service`：

```ini
[Unit]
Description=NepTune 爬取一次
After=network.target

[Service]
Type=oneshot
User=你的用户名
WorkingDirectory=/path/to/crawler
Environment=PATH=/path/to/crawler/.venv/bin
ExecStart=/path/to/crawler/.venv/bin/python -m src.run upwork
```

2. 写定时器，例如 `/etc/systemd/system/neptune-crawl.timer`：

```ini
[Unit]
Description=每天 9 点执行 NepTune 爬取
Requires=neptune-crawl.service

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=yes

[Install]
WantedBy=timers.target
```

3. 启用并启动定时器：

```bash
sudo systemctl daemon-reload
sudo systemctl enable neptune-crawl.timer
sudo systemctl start neptune-crawl.timer
sudo systemctl list-timers
```

如需改时区，可在 `[Service]` 里加 `Environment=TZ=Asia/Shanghai`。

### 方式 C：常驻调度进程（APScheduler）

若不想用 cron 或 systemd 定时器，可单独跑调度器（默认每天 9:00 执行一次）：

```bash
cd /path/to/crawler
source .venv/bin/activate
python -m src.run_scheduler
```

需常驻（如用 systemd 或 screen/tmux），并设置 `TZ`、`TELEGRAM_PUSH_HOUR`、`TELEGRAM_PUSH_MINUTE` 等环境变量控制时间与时区。

---

## 五、可选：Nginx 反代（对外 80/443）

若希望用域名 + HTTPS 访问网站，可在前面加 Nginx。示例（HTTP，仅作参考）：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    location / {
        proxy_pass http://127.0.0.1:5050;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

再配置 SSL（如 certbot）即可。

---

## 六、操作清单小结

| 步骤 | 操作 |
|------|------|
| 1 | 服务器安装 Python 3.10+，上传代码，配置 `.env` |
| 2 | `pip install -r requirements.txt` |
| 3 | 启动网站：`gunicorn` 或 systemd `neptune-web.service` |
| 4 | **部署后立即爬 100 条**：`python -m src.run upwork`（或加 `--clear` 清空再爬） |
| 5 | **每天 9 点爬取**：crontab 加 `0 9 * * * ... python -m src.run upwork`，或 systemd timer，或 `run_scheduler` |

数据与状态：SQLite 与爬取时间戳在 `DATA_DIR`（默认 `data/`），与网页、爬虫共用，无需额外配置。
