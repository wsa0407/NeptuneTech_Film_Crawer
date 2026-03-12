"""
测试：线索状态与模块的对应关系。

用例覆盖：
1. 跟进中 → 已转化：在跟进中模块将线索改为已转化后，该线索从跟进中列表消失，出现在已转化列表。
2. 待处理 → 已忽略、待处理 → 跟进中、跟进中 → 已忽略 等状态切换后，列表筛选正确。
"""
import os
import tempfile
import unittest
from pathlib import Path

# 使用临时目录作为 DATA_DIR，避免污染真实数据
def _set_data_dir():
    tmp = tempfile.mkdtemp(prefix="nep_crawler_test_")
    os.environ["DATA_DIR"] = tmp
    return tmp


def _fixture_lead(lead_id: str, **kwargs):
    from datetime import datetime, timezone
    base = {
        "id": lead_id,
        "platform": "upwork",
        "source_url": "https://example.com/job/" + lead_id,
        "title": "Test " + lead_id,
        "publisher": "publisher",
        "description": "desc",
        "budget_signal": None,
        "salary_raw": None,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(kwargs)
    return base


class TestLeadStatusModule(unittest.TestCase):
    def setUp(self):
        self._data_dir = _set_data_dir()
        from src.storage import store
        store.init_db()

    def tearDown(self):
        if "DATA_DIR" in os.environ and os.environ["DATA_DIR"] == self._data_dir:
            del os.environ["DATA_DIR"]
        try:
            import shutil
            shutil.rmtree(self._data_dir, ignore_errors=True)
        except Exception:
            pass

    def test_following_to_converted_lead_moves_to_converted_module(self):
        """CASE: 用户在跟进中模块将线索状态从 跟进中 调整为 已转化 时，该线索从跟进中列表消失，出现在已转化列表。"""
        from src.storage.store import insert_lead, set_follow_up, list_leads, get_follow_up

        lead_id = "test-f2c-001"
        insert_lead(_fixture_lead(lead_id))
        set_follow_up(lead_id, "following", "跟进中备注")

        # 改状态为已转化（模拟用户在跟进中页点击下拉选择「已转化」并提交）
        set_follow_up(lead_id, "converted", "")

        # 断言：跟进中列表不应包含该线索
        following_list, following_total = list_leads(status_filter="following", limit=100)
        following_ids = [l["id"] for l in following_list]
        self.assertNotIn(lead_id, following_ids, "改为已转化后，该线索不应再出现在跟进中模块")

        # 断言：已转化列表应包含该线索
        converted_list, converted_total = list_leads(status_filter="converted", limit=100)
        converted_ids = [l["id"] for l in converted_list]
        self.assertIn(lead_id, converted_ids, "改为已转化后，该线索应出现在已转化模块")

        fu = get_follow_up(lead_id)
        self.assertIsNotNone(fu)
        self.assertEqual(fu["status"], "converted")

    def test_pending_to_ignored_lead_moves_to_ignored_module(self):
        """待处理 → 已忽略：线索从待处理消失，出现在已忽略列表。"""
        from src.storage.store import insert_lead, set_follow_up, list_leads

        lead_id = "test-p2i-001"
        insert_lead(_fixture_lead(lead_id))
        # 初始无 follow_up 或 pending，在待处理列表
        set_follow_up(lead_id, "ignored", "不匹配需求")

        pending_list, _ = list_leads(status_filter="pending", limit=100)
        self.assertNotIn(lead_id, [l["id"] for l in pending_list])

        ignored_list, _ = list_leads(status_filter="ignored", limit=100)
        self.assertIn(lead_id, [l["id"] for l in ignored_list])

    def test_pending_to_following_lead_moves_to_following_module(self):
        """待处理 → 跟进中：线索从待处理消失，出现在跟进中列表。"""
        from src.storage.store import insert_lead, set_follow_up, list_leads

        lead_id = "test-p2f-001"
        insert_lead(_fixture_lead(lead_id))
        set_follow_up(lead_id, "following", "")

        pending_list, _ = list_leads(status_filter="pending", limit=100)
        self.assertNotIn(lead_id, [l["id"] for l in pending_list])

        following_list, _ = list_leads(status_filter="following", limit=100)
        self.assertIn(lead_id, [l["id"] for l in following_list])

    def test_following_to_ignored_lead_moves_to_ignored_module(self):
        """跟进中 → 已忽略：线索从跟进中消失，出现在已忽略列表。"""
        from src.storage.store import insert_lead, set_follow_up, list_leads

        lead_id = "test-f2i-001"
        insert_lead(_fixture_lead(lead_id))
        set_follow_up(lead_id, "following", "")
        set_follow_up(lead_id, "ignored", "岗位已下线")

        following_list, _ = list_leads(status_filter="following", limit=100)
        self.assertNotIn(lead_id, [l["id"] for l in following_list])

        ignored_list, _ = list_leads(status_filter="ignored", limit=100)
        self.assertIn(lead_id, [l["id"] for l in ignored_list])

    def test_ignored_revert_to_pending_lead_appears_in_pending(self):
        """已忽略 → 撤销(待处理)：线索从已忽略消失，出现在待处理列表。"""
        from src.storage.store import insert_lead, set_follow_up, list_leads

        lead_id = "test-i2p-001"
        insert_lead(_fixture_lead(lead_id))
        set_follow_up(lead_id, "ignored", "")
        set_follow_up(lead_id, "pending", "")

        ignored_list, _ = list_leads(status_filter="ignored", limit=100)
        self.assertNotIn(lead_id, [l["id"] for l in ignored_list])

        pending_list, _ = list_leads(status_filter="pending", limit=100)
        self.assertIn(lead_id, [l["id"] for l in pending_list])

    def test_pending_module_includes_lead_without_follow_up(self):
        """无跟进记录的线索出现在待处理列表。"""
        from src.storage.store import insert_lead, list_leads

        lead_id = "test-no-fu-001"
        insert_lead(_fixture_lead(lead_id))
        # 不调用 set_follow_up

        pending_list, _ = list_leads(status_filter="pending", limit=100)
        self.assertIn(lead_id, [l["id"] for l in pending_list])

        following_list, _ = list_leads(status_filter="following", limit=100)
        self.assertNotIn(lead_id, [l["id"] for l in following_list])
