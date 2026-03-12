"""
一次性脚本：把 leads.db 里所有「待处理」的 Upwork 线索的 source_url 改为
https://www.upwork.com/jobs/~02{uid}，其中 uid 为 lead id 去掉前缀 upwork_ 的部分（与 Apify 返回格式一致）。
"""
import sqlite3
import sys
from pathlib import Path

# 项目根为 crawler/
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.store import get_db_path


def main() -> None:
    path = get_db_path()
    if not path.exists():
        print("leads.db 不存在，退出")
        return
    with sqlite3.connect(str(path)) as conn:
        # 待处理 = 无 follow_up 或 follow_up.status = 'pending'
        cur = conn.execute(
            """
            UPDATE leads
            SET source_url = 'https://www.upwork.com/jobs/~02' || SUBSTR(id, 8)
            WHERE platform = 'upwork'
              AND (id NOT IN (SELECT lead_id FROM lead_follow_ups)
                   OR id IN (SELECT lead_id FROM lead_follow_ups WHERE status = 'pending'))
            """
        )
        updated = cur.rowcount
    print(f"已更新 {updated} 条待处理 Upwork 线索的 source_url")


if __name__ == "__main__":
    main()
