"""
每日 9 点执行抓取并推送 Telegram。常驻运行，到点自动跑。
"""
import logging
import os
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.run import run_crawl_and_push

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def job() -> None:
    logger.info("定时任务: 开始抓取并推送")
    run_crawl_and_push(platform="upwork", dry_run=False, skip_telegram=False)
    logger.info("定时任务: 完成")


def main() -> int:
    hour = int(os.environ.get("TELEGRAM_PUSH_HOUR", "9"))
    minute = int(os.environ.get("TELEGRAM_PUSH_MINUTE", "0"))
    tz = os.environ.get("TZ", "Asia/Shanghai")

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(job, CronTrigger(hour=hour, minute=minute))
    logger.info("已设置每日 %02d:%02d (%s) 执行抓取并推送 Telegram，按 Ctrl+C 退出", hour, minute, tz)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
