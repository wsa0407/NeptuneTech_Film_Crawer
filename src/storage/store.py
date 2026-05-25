"""
SQLite 存储：线索表结构与写入接口。
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.crawlers.base import get_data_dir


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    source_url TEXT,
    title TEXT,
    publisher TEXT,
    description TEXT,
    budget_signal TEXT,
    salary_raw TEXT,
    extra_json TEXT,
    published_at TEXT,
    crawled_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_platform ON leads(platform);
CREATE INDEX IF NOT EXISTS idx_leads_crawled_at ON leads(crawled_at);

CREATE TABLE IF NOT EXISTS lead_follow_ups (
    lead_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);
CREATE INDEX IF NOT EXISTS idx_follow_ups_status ON lead_follow_ups(status);

CREATE TABLE IF NOT EXISTS crawl_state (
    platform TEXT PRIMARY KEY,
    last_crawl_at TEXT NOT NULL
);
"""


def get_db_path() -> Path:
    d = get_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "leads.db"


def init_db() -> None:
    path = get_db_path()
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(TABLE_SQL)


def get_last_crawl_at(platform: str) -> str | None:
    """返回某平台上次爬取完成时间（ISO 字符串），未爬过返回 None。"""
    path = get_db_path()
    if not path.exists():
        return None
    with sqlite3.connect(str(path)) as conn:
        row = conn.execute(
            "SELECT last_crawl_at FROM crawl_state WHERE platform = ?",
            (platform,),
        ).fetchone()
    return row[0] if row else None


def set_last_crawl_at(platform: str, at: str) -> None:
    """记录某平台本次爬取完成时间。"""
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO crawl_state (platform, last_crawl_at) VALUES (?, ?)",
            (platform, at),
        )


def clear_all_leads() -> None:
    """清空所有线索与跟进记录，并清除爬取状态，便于重新「首次 100 条」."""
    path = get_db_path()
    if not path.exists():
        return
    with sqlite3.connect(str(path)) as conn:
        conn.execute("DELETE FROM lead_follow_ups")
        conn.execute("DELETE FROM leads")
        conn.execute("DELETE FROM crawl_state")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_lead(lead: dict[str, Any]) -> None:
    """插入一条线索，若 id 已存在则忽略（避免重复）。"""
    path = get_db_path()
    row = (
        lead.get("id", ""),
        lead.get("platform", ""),
        lead.get("source_url"),
        lead.get("title"),
        lead.get("publisher"),
        lead.get("description"),
        lead.get("budget_signal"),
        lead.get("salary_raw"),
        json.dumps(lead.get("extra") or {}, ensure_ascii=False) if lead.get("extra") else None,
        lead.get("published_at"),
        lead.get("crawled_at", _now_iso()),
    )
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO leads
            (id, platform, source_url, title, publisher, description, budget_signal, salary_raw, extra_json, published_at, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )


def insert_leads(leads: list[dict[str, Any]]) -> int:
    """批量插入，返回实际插入条数。"""
    path = get_db_path()
    now = _now_iso()
    rows = []
    for lead in leads:
        rows.append((
            lead.get("id", ""),
            lead.get("platform", ""),
            lead.get("source_url"),
            lead.get("title"),
            lead.get("publisher"),
            lead.get("description"),
            lead.get("budget_signal"),
            lead.get("salary_raw"),
            json.dumps(lead.get("extra") or {}, ensure_ascii=False) if lead.get("extra") else None,
            lead.get("published_at"),
            lead.get("crawled_at", now),
        ))
    with sqlite3.connect(str(path)) as conn:
        cur = conn.executemany(
            """
            INSERT OR IGNORE INTO leads
            (id, platform, source_url, title, publisher, description, budget_signal, salary_raw, extra_json, published_at, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return cur.rowcount if hasattr(cur, "rowcount") else len(rows)


def get_recent_leads(limit: int | None = None, platform: str | None = None) -> list[dict[str, Any]]:
    """读取最近爬取的线索，按 crawled_at 倒序。"""
    path = get_db_path()
    if not path.exists():
        return []
    sql = "SELECT id, platform, source_url, title, publisher, description, budget_signal, salary_raw, extra_json, published_at, crawled_at FROM leads ORDER BY crawled_at DESC"
    params: tuple = ()
    if platform:
        sql = "SELECT id, platform, source_url, title, publisher, description, budget_signal, salary_raw, extra_json, published_at, crawled_at FROM leads WHERE platform = ? ORDER BY crawled_at DESC"
        params = (platform,)
    if limit is not None:
        sql += " LIMIT ?"
        params = params + (limit,)
    with sqlite3.connect(str(path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
    out = []
    for r in rows:
        extra = {}
        if r["extra_json"]:
            try:
                extra = json.loads(r["extra_json"])
            except Exception:
                pass
        out.append({
            "id": r["id"],
            "platform": r["platform"],
            "source_url": r["source_url"],
            "title": r["title"],
            "publisher": r["publisher"],
            "description": r["description"] or "",
            "budget_signal": r["budget_signal"],
            "salary_raw": r["salary_raw"],
            "extra": extra,
            "published_at": r["published_at"],
            "crawled_at": r["crawled_at"],
        })
    return out


def update_lead_extra(lead_id: str, extra: dict[str, Any]) -> None:
    """更新一条线索的 extra_json（完整替换）。用于回填 core_summary 等。"""
    path = get_db_path()
    if not path.exists():
        return
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            "UPDATE leads SET extra_json = ? WHERE id = ?",
            (json.dumps(extra or {}, ensure_ascii=False), lead_id),
        )


def get_lead_by_id(lead_id: str) -> dict[str, Any] | None:
    """按 id 读取单条线索，不存在返回 None。"""
    path = get_db_path()
    if not path.exists():
        return None
    with sqlite3.connect(str(path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, platform, source_url, title, publisher, description, budget_signal, salary_raw, extra_json, published_at, crawled_at FROM leads WHERE id = ?",
            (lead_id,),
        )
        r = cur.fetchone()
    if not r:
        return None
    extra = {}
    if r["extra_json"]:
        try:
            extra = json.loads(r["extra_json"])
        except Exception:
            pass
    return {
        "id": r["id"],
        "platform": r["platform"],
        "source_url": r["source_url"],
        "title": r["title"],
        "publisher": r["publisher"],
        "description": r["description"] or "",
        "budget_signal": r["budget_signal"],
        "salary_raw": r["salary_raw"],
        "extra": extra,
        "published_at": r["published_at"],
        "crawled_at": r["crawled_at"],
    }


def list_leads(
    platform: str | None = None,
    published_from: str | None = None,
    published_to: str | None = None,
    search: str | None = None,
    status_filter: str | None = None,
    limit: int = 100,
    offset: int = 0,
    order_by: str = "crawled_at",
    order_dir: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    """分页列出线索，支持平台、发布时间范围、关键词、状态筛选。返回 (列表, 总条数)。
    order_by: 'crawled_at' 按抓取时间；'published_at' 按发布时间降序（新在前）。无发布时间排最后。order_dir 保留兼容。"""
    path = get_db_path()
    if not path.exists():
        return [], 0
    conditions = []
    params: list = []
    if platform:
        conditions.append("leads.platform = ?")
        params.append(platform)
    if published_from:
        # 有发布时间则按发布时间筛；无则按抓取时间兜底，保证筛选有效
        conditions.append("(leads.published_at >= ? OR (leads.published_at IS NULL AND leads.crawled_at >= ?))")
        params.extend([published_from, published_from])
    if published_to:
        conditions.append("leads.published_at <= ?")
        params.append(published_to)
    if search and search.strip():
        conditions.append("(leads.title LIKE ? OR leads.description LIKE ?)")
        q = "%" + search.strip() + "%"
        params.extend([q, q])
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    # 状态与模块一致：待处理=无记录或 pending，其它=对应 status 的 INNER JOIN
    if status_filter == "pending":
        join = " LEFT JOIN lead_follow_ups ON leads.id = lead_follow_ups.lead_id "
        status_cond = " (lead_follow_ups.lead_id IS NULL OR lead_follow_ups.status = 'pending')"
        where = (where + " AND " + status_cond) if where else (" WHERE " + status_cond)
    elif status_filter in ("following", "converted", "ignored"):
        join = " INNER JOIN lead_follow_ups ON leads.id = lead_follow_ups.lead_id AND lead_follow_ups.status = ? "
        params = [status_filter] + params
    else:
        join = ""
    from_clause = " FROM leads " + join
    if order_by == "published_at":
        asc = order_dir.lower() == "asc"
        order_sql = " ORDER BY leads.published_at IS NULL, leads.published_at ASC" if asc else " ORDER BY leads.published_at IS NULL, leads.published_at DESC"
    else:
        order_sql = " ORDER BY leads.crawled_at DESC"
    with sqlite3.connect(str(path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT COUNT(*) " + from_clause + where,
            params,
        )
        total = cur.fetchone()[0]
        cur = conn.execute(
            "SELECT leads.id, leads.platform, leads.source_url, leads.title, leads.publisher, leads.description, "
            "leads.budget_signal, leads.salary_raw, leads.extra_json, leads.published_at, leads.crawled_at "
            + from_clause + where + order_sql + " LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        extra = {}
        raw = r["extra_json"] if "extra_json" in r.keys() else r.get("extra_json")
        if raw:
            try:
                extra = json.loads(raw)
            except Exception:
                pass
        out.append({
            "id": r["id"],
            "platform": r["platform"],
            "source_url": r["source_url"],
            "title": r["title"],
            "publisher": r["publisher"],
            "description": (r["description"] or ""),
            "budget_signal": r["budget_signal"],
            "salary_raw": r["salary_raw"],
            "extra": extra,
            "published_at": r["published_at"],
            "crawled_at": r["crawled_at"],
        })
    return out, total


def get_follow_up(lead_id: str) -> dict[str, Any] | None:
    """读取一条线索的跟进信息，无则返回 None。"""
    path = get_db_path()
    if not path.exists():
        return None
    with sqlite3.connect(str(path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT lead_id, status, notes, updated_at FROM lead_follow_ups WHERE lead_id = ?",
            (lead_id,),
        )
        r = cur.fetchone()
    if not r:
        return None
    return {
        "lead_id": r["lead_id"],
        "status": r["status"] or "pending",
        "notes": r["notes"] or "",
        "updated_at": r["updated_at"],
    }


def set_follow_up(lead_id: str, status: str, notes: str) -> None:
    """写入或更新一条线索的跟进信息。"""
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    now = _now_iso()
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            "INSERT INTO lead_follow_ups (lead_id, status, notes, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(lead_id) DO UPDATE SET status = excluded.status, notes = excluded.notes, updated_at = excluded.updated_at",
            (lead_id, status, notes, now),
        )
