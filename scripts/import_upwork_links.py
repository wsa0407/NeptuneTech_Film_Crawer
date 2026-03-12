"""
手动导入 Upwork 职位链接：不依赖 RSS，把链接列表导入库并可选推送 Telegram。
用法：
  1. 在浏览器里打开 Upwork 搜索（过完真人验证后），复制想跟进的职位详情页链接。
  2. 每行一个链接，保存到 data/upwork_links.txt（或任意文本文件）。
  3. 运行：python scripts/import_upwork_links.py [文件路径]
  4. 默认会导入并推送到 Telegram；加 --no-telegram 只导入不推送。
链接格式示例：
  https://www.upwork.com/freelance-jobs/apply/Video-Series-Creator_~022026170044277888904/
  https://www.upwork.com/nx/search/jobs/details/~01abc...
"""
import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.storage.store import init_db, insert_lead
from src.telegram_notify import push_leads

BASE_URL = "https://www.upwork.com"


def _extract_job_id(url: str) -> str:
    m = re.search(r"_~([0-9a-f]+)(?:/|$|\?)", url)
    if m:
        return m.group(1)
    m = re.search(r"/jobs/details/~([a-f0-9]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/jobs/~([a-f0-9]+)", url)
    return m.group(1) if m else ""


def _slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[-\s]+", "-", s.strip())
    return s[:80] if s else "Job"


def _detail_url(job_id: str, title: str) -> str:
    slug = _slugify(title)
    return f"{BASE_URL}/freelance-jobs/apply/{slug}_~{job_id}/"


def main():
    parser = argparse.ArgumentParser(description="从文本文件导入 Upwork 职位链接")
    parser.add_argument("file", nargs="?", default=None, help="每行一个链接，默认 data/upwork_links.txt")
    parser.add_argument("--no-telegram", action="store_true", help="只导入，不推送 Telegram")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    path = Path(args.file) if args.file else root / "data" / "upwork_links.txt"
    if not path.exists():
        print(f"文件不存在: {path}")
        print("请创建该文件，每行粘贴一个 Upwork 职位详情页链接。")
        return 1

    lines = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
    urls = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            title, url = line.split("\t", 1)
            title, url = title.strip(), url.strip()
        elif "," in line:
            title, url = line.split(",", 1)
            title, url = title.strip(), url.strip()
        else:
            title, url = "", line
        if "upwork.com" in (url or "") and "/jobs/" in (url or ""):
            urls.append((title or "Upwork Job", url))

    if not urls:
        print("未找到有效链接，请检查文件格式（每行一个 URL，或 标题\\tURL）。")
        return 1

    init_db()
    leads = []
    for title, url in urls:
        job_id = _extract_job_id(url)
        if not job_id:
            print("跳过（无法解析 job_id）:", url[:60])
            continue
        detail = _detail_url(job_id, title)
        lead = {
            "id": f"upwork_{job_id}",
            "platform": "upwork",
            "source_url": detail,
            "title": title,
            "publisher": "—",
            "description": "",
            "budget_signal": None,
            "salary_raw": None,
            "extra": {"source": "manual_import"},
            "published_at": None,
            "crawled_at": datetime.now(timezone.utc).isoformat(),
        }
        insert_lead(lead)
        leads.append(lead)
        print("导入:", title[:50], detail)

    print(f"共导入 {len(leads)} 条。")
    if not args.no_telegram and leads:
        sent = push_leads(leads)
        print(f"已推送 Telegram: {sent} 条。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
