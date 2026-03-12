"""
Telegram 推送：将线索按 PRD 格式发送到指定群组/私聊。
若 .env 未填 TELEGRAM_CHAT_ID，会尝试从 getUpdates 获取并写回 .env 后推送。
"""
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BASE_URL = "https://api.telegram.org/bot"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


def _format_posted_time(published_at: str | None) -> str:
    """将 published_at（ISO 或日期字符串）格式化为「昨天发布」「X小时前」等。"""
    if not published_at or not str(published_at).strip():
        return "—"
    raw = str(published_at).strip()
    try:
        if "T" in raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        if delta < timedelta(hours=1):
            return "1小时内发布"
        if delta < timedelta(hours=24):
            h = int(delta.total_seconds() // 3600)
            return f"{h}小时前发布"
        if delta < timedelta(hours=48):
            return "昨天发布"
        if delta < timedelta(days=7):
            return f"{delta.days}天前发布"
        return dt.strftime("%Y-%m-%d 发布")
    except Exception:
        return raw[:30] if len(raw) > 30 else raw or "—"


def _get_chat_id_from_updates(token: str) -> str:
    """从 getUpdates 取最近一次聊天的 chat_id。"""
    url = f"{BASE_URL}{token}/getUpdates"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        for u in reversed(data.get("result") or []):
            cid = (u.get("message") or u.get("channel_post") or {}).get("chat", {}).get("id")
            if cid is not None:
                return str(cid)
    except Exception as e:
        logger.warning("getUpdates 失败: %s", e)
    return ""


def _save_chat_id_to_env(chat_id: str) -> bool:
    """把 TELEGRAM_CHAT_ID 写入 .env。"""
    try:
        if ENV_PATH.exists():
            raw = ENV_PATH.read_text(encoding="utf-8")
            if re.search(r"^\s*TELEGRAM_CHAT_ID\s*=", raw, re.M):
                raw = re.sub(
                    r"^(\s*TELEGRAM_CHAT_ID\s*=\s*).*$",
                    r"\g<1>" + chat_id,
                    raw,
                    count=1,
                    flags=re.M,
                )
            else:
                raw = raw.rstrip() + "\nTELEGRAM_CHAT_ID=" + chat_id + "\n"
        else:
            raw = "TELEGRAM_CHAT_ID=" + chat_id + "\n"
        ENV_PATH.write_text(raw, encoding="utf-8")
        os.environ["TELEGRAM_CHAT_ID"] = chat_id
        return True
    except Exception as e:
        logger.warning("写入 .env 失败: %s", e)
        return False


def _escape(s: str) -> str:
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_lead_message(lead: dict[str, Any]) -> str:
    """单条线索卡片：发布时间、平台、标题、工作地点、预算、核心描述、直达链接。缺项用 —。"""
    extra = lead.get("extra") or {}
    platform = (lead.get("platform") or "upwork").lower()
    platform_label = "Upwork" if platform == "upwork" else platform
    title = (lead.get("title") or "").strip()
    title = _escape(title) if title else "—"
    description = (lead.get("description") or "").strip()
    core_summary = lead.get("core_summary") or extra.get("core_summary")
    if core_summary and str(core_summary).strip():
        core_desc = _escape(str(core_summary).strip())
    elif description:
        core_desc = _escape(description[:80].strip() + ("…" if len(description) > 80 else ""))
    else:
        core_desc = "—"
    budget_raw = lead.get("budget_signal") or lead.get("salary_raw") or extra.get("hourly_range") or extra.get("fixed_budget")
    if isinstance(budget_raw, str) and budget_raw.strip():
        budget = _escape(budget_raw.strip())
    else:
        budget = "—"
    work_location = (extra.get("work_location") or "").strip()
    work_location = _escape(work_location) if work_location else "—"
    url = lead.get("source_url") or ""
    url = url.strip() if url else "—"
    posted_time = _format_posted_time(lead.get("published_at"))

    return f"""🕐 发布时间：{posted_time}
🎯 新线索：[{platform_label}]
📝 需求标题：{title}
📍 工作地点：{work_location}
💰 预算信号：{budget}
🔍 核心描述：{core_desc}
🔗 直达链接：{url}"""


def send_message(token: str, chat_id: str, text: str) -> bool:
    """发送一条消息，返回是否成功。"""
    url = f"{BASE_URL}{token}/sendMessage"
    body = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.getcode() == 200
    except urllib.error.HTTPError as e:
        logger.warning("Telegram API error: %s %s", e.code, e.read().decode()[:200])
        return False
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)
        return False


SUMMARY_LINK = "https://soraplayground.com"


def format_summary_message(lead_count: int) -> str:
    """单条汇总：完成时间（东八区）、线索数量、soraplayground.com 链接。"""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
    except ImportError:
        tz = timezone.utc
    now = datetime.now(tz)
    done_at = now.strftime("%Y-%m-%d %H:%M:%S")
    return f"""✅ 爬取完成
🕐 完成时间：{done_at}
📊 线索数量：{lead_count} 条
🔗 查看线索：{SUMMARY_LINK}"""


def push_leads(leads: list[dict[str, Any]], interval_sec: float = 1.1) -> int:
    """
    向 Telegram 发送一条汇总消息（完成时间、线索数量、soraplayground.com 链接），不再逐条发送线索。
    若 TELEGRAM_CHAT_ID 未配置，会尝试从 getUpdates 获取并写回 .env。
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        logger.warning("Telegram 未推送：.env 中未配置 TELEGRAM_BOT_TOKEN")
        return 0
    if not chat_id and leads:
        logger.info("TELEGRAM_CHAT_ID 未配置，正在从 getUpdates 获取...")
        chat_id = _get_chat_id_from_updates(token)
        if chat_id:
            _save_chat_id_to_env(chat_id)
            logger.info("已获取 chat_id 并写入 .env，开始推送")
        else:
            logger.warning(
                "无法获取 chat_id：请先在 Telegram 里给 Bot 发一条任意消息，然后重新运行（或执行 python scripts/test_telegram_bot.py）"
            )
            return 0
    if not chat_id:
        logger.warning("Telegram 未推送：未配置 TELEGRAM_CHAT_ID 且 getUpdates 无记录")
        return 0
    if not leads:
        logger.info("无新线索，跳过 Telegram 推送")
        return 0

    text = format_summary_message(len(leads))
    if send_message(token, chat_id, text):
        logger.info("Telegram 已推送汇总（%d 条线索）", len(leads))
        return 1
    logger.warning("Telegram 推送失败")
    return 0
