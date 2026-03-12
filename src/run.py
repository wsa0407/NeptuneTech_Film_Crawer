"""
入口：按平台执行抓取，支持 --platform、--dry-run、Telegram 推送。
"""
import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# 保证从项目根可执行：python -m src.run 或 python src/run.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.crawlers.upwork import crawl_upwork
from src.gemini_summary import enrich_leads_with_summary
from src.storage.store import init_db, clear_all_leads, insert_leads, set_last_crawl_at
from src.telegram_notify import push_leads

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_crawl_and_push(
    platform: str,
    dry_run: bool,
    skip_telegram: bool,
    max_leads: int | None = None,
    clear: bool = False,
    from_date: str | None = None,
    to_date: str | None = None,
) -> int:
    """执行抓取并在有配置时推送 Telegram。Upwork 需传入 from_date / to_date（发布时间范围）。clear=True 时先清空历史再爬。返回 0 表示成功。"""
    if clear:
        init_db()
        clear_all_leads()
        logger.info("已清空所有线索、跟进记录与爬取状态，本次将按「首次 100 条」执行")
    all_leads = []
    if platform in ("upwork", "all"):
        if not from_date or not to_date:
            logger.error("Upwork 爬虫需要指定发布时间范围，请使用 --from-date 和 --to-date，例如：--from-date 2025-01-01 --to-date 2025-12-31")
            return 1
        n, leads = crawl_upwork(from_date=from_date, to_date=to_date, dry_run=dry_run, max_leads=max_leads)
        logger.info("Upwork: %d leads", n)
        all_leads.extend(leads)
        if not dry_run and all_leads:
            enrich_leads_with_summary(all_leads)
            insert_leads(all_leads)
            set_last_crawl_at("upwork", datetime.now(timezone.utc).isoformat())
            logger.info("Upwork: 已入库 %d 条并更新 last_crawl_at", len(all_leads))
    if platform == "backstage":
        logger.warning("Backstage crawler not implemented yet")
    if platform == "linkedin":
        logger.warning("LinkedIn crawler not implemented yet")

    if not skip_telegram and all_leads:
        if platform not in ("upwork", "all") or dry_run:
            enrich_leads_with_summary(all_leads)
        logger.info("准备推送 %d 条到 Telegram...", len(all_leads))
        sent = push_leads(all_leads)
        logger.info("Telegram 推送: %d 条", sent)
        if sent == 0 and all_leads:
            logger.warning("有 %d 条线索但 Telegram 未发送成功，请检查 .env 或先给 Bot 发一条消息后重试", len(all_leads))
    elif not skip_telegram and not all_leads:
        logger.info("本次抓取 0 条，无内容可推送")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="NepTune 招聘线索抓取")
    parser.add_argument(
        "platform_pos",
        nargs="?",
        default=None,
        choices=["upwork", "backstage", "linkedin", "all"],
        help="平台（可选，与 --platform 二选一）",
    )
    parser.add_argument(
        "--platform",
        choices=["upwork", "backstage", "linkedin", "all"],
        default=None,
        help="要执行的爬虫",
    )
    parser.add_argument("--dry-run", action="store_true", help="只跑不落库")
    parser.add_argument("--no-telegram", action="store_true", help="本次不推送 Telegram")
    parser.add_argument(
        "--max-leads",
        type=int,
        default=None,
        metavar="N",
        help="首次爬取时最多 N 条，默认 100；设为 0 表示不限制",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="清空历史线索与跟进记录后再爬（之后按「首次 100 条」逻辑）",
    )
    parser.add_argument(
        "--clear-only",
        action="store_true",
        help="仅清空线索库（leads、跟进记录、爬取状态），不执行抓取",
    )
    parser.add_argument(
        "--from-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Upwork：岗位发布时间起（必填），例如 2025-01-01",
    )
    parser.add_argument(
        "--to-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Upwork：岗位发布时间止（必填），例如 2025-12-31",
    )
    args = parser.parse_args()

    if args.clear_only:
        init_db()
        clear_all_leads()
        logger.info("已清空线索库（leads、lead_follow_ups、crawl_state）")
        return 0

    platform = args.platform or args.platform_pos or "upwork"
    max_leads = None if args.max_leads == 0 else args.max_leads
    return run_crawl_and_push(
        platform,
        args.dry_run,
        args.no_telegram,
        max_leads,
        clear=args.clear,
        from_date=args.from_date,
        to_date=args.to_date,
    )


if __name__ == "__main__":
    raise SystemExit(main())
