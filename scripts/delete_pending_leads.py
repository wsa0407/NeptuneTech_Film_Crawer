"""
一次性脚本：删除 leads.db 中所有「待处理」的线索。
待处理 = 无 follow_up 记录 或 follow_up.status = 'pending'。
"""
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.store import get_db_path


def main() -> None:
    path = get_db_path()
    if not path.exists():
        print("leads.db 不存在，退出")
        return
    with sqlite3.connect(str(path)) as conn:
        # 待处理 lead_id 集合：无 follow_up 或 status=pending
        cur = conn.execute(
            """
            SELECT id FROM leads
            WHERE id NOT IN (SELECT lead_id FROM lead_follow_ups)
               OR id IN (SELECT lead_id FROM lead_follow_ups WHERE status = 'pending')
            """
        )
        pending_ids = [row[0] for row in cur.fetchall()]
        if not pending_ids:
            print("没有待处理数据")
            return
        n_pending = len(pending_ids)
        # 先删 follow_ups 中的 pending 记录，再删 leads（避免外键问题）
        conn.execute("DELETE FROM lead_follow_ups WHERE status = 'pending'")
        conn.execute(
            "DELETE FROM leads WHERE id NOT IN (SELECT lead_id FROM lead_follow_ups)"
        )
        conn.commit()
    print(f"已删除 {n_pending} 条待处理线索")


if __name__ == "__main__":
    main()
