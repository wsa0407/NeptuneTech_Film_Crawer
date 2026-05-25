#!/usr/bin/env python3
"""
回填脚本：用当前配置的摘要模型（DeepSeek）对 data/leads.db 中所有线索的 description 重新生成中文总结，
并写入 extra_json.core_summary。CRM 详情页「完整描述」会优先展示 core_summary，因此会显示新的总结。

用法（项目根目录）：
  python scripts/backfill_core_summary.py                 # 对有描述的线索全部重新总结并写库
  python scripts/backfill_core_summary.py --missing-only # 仅补充尚未写入 core_summary 的线索
  python scripts/backfill_core_summary.py --dry-run       # 仅打印将要处理的条数，不写库

需配置 .env 中 VOLCANO_API_KEY 或 ARK_API_KEY、可选 VOLCANO_MODEL。
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="回填 leads 的 core_summary（中文总结）")
    parser.add_argument("--dry-run", action="store_true", help="只统计条数，不调用 API、不写库")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="仅处理 extra_json 中尚无 core_summary（或为空）的线索，避免重复打 API",
    )
    args = parser.parse_args()

    from src.storage.store import get_recent_leads, update_lead_extra
    from src.gemini_summary import summarize_description

    leads = get_recent_leads(limit=None)
    # 只处理有足够描述内容的
    to_process = [l for l in leads if (l.get("description") or "").strip() and len((l.get("description") or "").strip()) >= 10]
    if args.missing_only:
        def _no_summary(row: dict) -> bool:
            extra = row.get("extra") or {}
            return not (str(extra.get("core_summary") or "").strip())

        to_process = [l for l in to_process if _no_summary(l)]
    logger.info("共 %d 条线索，其中 %d 条将处理", len(leads), len(to_process))

    if args.dry_run:
        for i, lead in enumerate(to_process[:5], 1):
            logger.info("  [示例 %d] id=%s title=%s", i, lead.get("id"), (lead.get("title") or "")[:50])
        if len(to_process) > 5:
            logger.info("  ... 共 %d 条", len(to_process))
        return

    if not to_process:
        logger.info("没有需要处理的线索")
        return

    ok = 0
    fail = 0
    for i, lead in enumerate(to_process, 1):
        lead_id = lead.get("id", "")
        title = (lead.get("title") or "")[:50]
        description = (lead.get("description") or "").strip()
        summary = summarize_description(description)
        if summary:
            extra = dict(lead.get("extra") or {})
            extra["core_summary"] = summary
            update_lead_extra(lead_id, extra)
            ok += 1
            logger.info("[%d/%d] 已更新 core_summary id=%s %s", i, len(to_process), lead_id, title)
        else:
            fail += 1
            logger.warning("[%d/%d] 摘要失败，跳过 id=%s %s", i, len(to_process), lead_id, title)

    logger.info("回填完成：成功 %d，失败/跳过 %d", ok, fail)


if __name__ == "__main__":
    main()
