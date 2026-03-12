"""
把数据库里最近爬取的线索推送到 Telegram（不重新爬）。
用法：python scripts/push_recent_to_telegram.py [--limit N] [--platform upwork]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.storage.store import get_recent_leads
from src.telegram_notify import push_leads

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将库内最近线索推送到 Telegram")
    parser.add_argument("--limit", type=int, default=50, help="最多推送条数，默认 50")
    parser.add_argument("--platform", type=str, default=None, help="只推送该平台，如 upwork")
    args = parser.parse_args()

    leads = get_recent_leads(limit=args.limit, platform=args.platform)
    if not leads:
        print("数据库中没有线索，请先运行爬虫。")
        sys.exit(1)
    print(f"共 {len(leads)} 条，正在推送到 Telegram...")
    sent = push_leads(leads)
    print(f"已推送 {sent} 条。")
    sys.exit(0 if sent else 1)
