"""
Upwork 定向采集器（Apify 模式）。
通过 Apify Actor the-empire-strikes-back/upwork-scraper 抓取 Upwork 职位，按关键词列表逐条搜索、合并去重后入库并支持 Telegram 推送。
需在 .env 中配置 APIFY_API_TOKEN。
"""
import html as html_module
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from src.crawlers.base import load_yaml
from src.storage.store import init_db, get_last_crawl_at

logger = logging.getLogger(__name__)

PLATFORM = "upwork"
APIFY_ACTOR_ID = "the-empire-strikes-back/upwork-scraper"


def _strip_html(text: str | None, preserve_newlines: bool = False) -> str:
    """去掉 HTML 标签并解码实体，得到纯文本。
    preserve_newlines=True 时保留换行（用于完整描述），否则所有空白压成空格。"""
    if text is None:
        return ""
    s = str(text).strip()
    if not s:
        return ""
    s = html_module.unescape(s)
    s = re.sub(r"<[^>]+>", "", s)
    if preserve_newlines:
        s = re.sub(r"\r\n?", "\n", s)
        s = re.sub(r"[ \t]+", " ", s)
        return s.strip()
    return re.sub(r"\s+", " ", s).strip()


def _extract_job_id_from_url(url: str) -> str:
    """从 Upwork 职位 URL 中解析 job_id（支持 ~ 格式）。"""
    if not url:
        return ""
    m = re.search(r"_~([0-9a-f]+)(?:/|$|\?)", url)
    if m:
        return m.group(1)
    m = re.search(r"/jobs/details/~([a-f0-9]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/jobs/~([a-f0-9]+)", url) or re.search(r"/jobs/([^/?]+)", url)
    return m.group(1) if m else ""


def _detail_url_direct(job_id: str, base_url: str = "https://www.upwork.com") -> str:
    """详情页直连 URL：/nx/search/jobs/details/~{job_id}"""
    base_url = base_url.rstrip("/")
    return f"{base_url}/nx/search/jobs/details/~{job_id}"


def _lead_from_apify_item(item: dict[str, Any], base_url: str) -> dict[str, Any] | None:
    """将 Apify Actor 输出的一条 item 转为 lead。Actor 输出为 snake_case：description_text, publish_time, budget_total_usd 等。"""
    url = (item.get("url") or item.get("jobUrl") or item.get("link") or "").strip()
    job_id = (item.get("job_id") or "").strip() or (_extract_job_id_from_url(url) if url else "")
    if not job_id:
        job_id = (item.get("jobId") or item.get("id") or "").strip()
    title = (item.get("title") or item.get("jobTitle") or item.get("name") or "").strip()
    title = _strip_html(title)
    if not title or len(title) < 2:
        return None
    description = (
        item.get("description_text")
        or item.get("description")
        or item.get("snippet")
        or item.get("body")
        or ""
    )
    if isinstance(description, str):
        description = _strip_html(description, preserve_newlines=True)
    else:
        description = ""
    hourly_str = ""
    lo, hi = item.get("budget_hourly_min_usd"), item.get("budget_hourly_max_usd")
    if lo is not None and hi is not None:
        hourly_str = f"${lo}-${hi}/hr"
    elif lo is not None:
        hourly_str = f"${lo}/hr"
    elif hi is not None:
        hourly_str = f"${hi}/hr"
    fixed_str = ""
    total = item.get("budget_total_usd")
    if total is not None:
        fixed_str = f"${total}"
    if not hourly_str and not fixed_str:
        budget_raw = (
            item.get("budget")
            or item.get("amount")
            or item.get("budgetAmount")
            or item.get("salary")
            or ""
        )
        if isinstance(budget_raw, dict):
            budget_raw = budget_raw.get("amount") or budget_raw.get("min") or str(budget_raw)
        if budget_raw:
            fixed_str = str(budget_raw).strip()
    parts = []
    if hourly_str:
        parts.append(f"时薪 {hourly_str}")
    if fixed_str:
        parts.append(f"固定 {fixed_str}")
    budget_str = " | ".join(parts) if parts else (fixed_str or hourly_str or "")
    source_url = url or _detail_url_direct(job_id, base_url)
    posted = (
        item.get("publish_time")
        or item.get("postedOn")
        or item.get("publishedAt")
        or item.get("createdAt")
        or item.get("posted_at")
    )
    if hasattr(posted, "isoformat"):
        posted = posted.isoformat()
    posted_str = str(posted).strip() if posted else None
    work_location = (
        item.get("location")
        or item.get("job_location")
        or item.get("client_location")
        or item.get("client_country")
        or item.get("client_city")
        or item.get("country")
        or item.get("workLocation")
        or item.get("clientCountry")
        or ""
    )
    work_location = str(work_location).strip() if work_location else ""
    extra = {"source": "apify"}
    if work_location:
        extra["work_location"] = work_location
    if hourly_str:
        extra["hourly_range"] = hourly_str
    if fixed_str:
        extra["fixed_budget"] = fixed_str
    return _make_lead(
        job_id=job_id or f"apify_{hash(url) % 10**10}",
        title=title,
        source_url=source_url,
        publisher=(item.get("clientName") or item.get("client") or "—").strip() or "—",
        description=description,
        budget_signal=budget_str,
        extra=extra,
        published_at=posted_str,
        salary_raw=budget_str or None,
    )


def _parse_published_at(s: str | None) -> datetime | None:
    """将发布时间字符串解析为 UTC datetime，便于与 last_crawl_at 比较。解析失败返回 None。"""
    if not s or not str(s).strip():
        return None
    raw = str(s).strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw[:19] if "T" in raw else raw[:10], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _make_lead(
    job_id: str,
    title: str,
    source_url: str,
    publisher: str,
    description: str,
    budget_signal: str,
    extra: dict,
    published_at: str | None,
    salary_raw: str | None = None,
) -> dict[str, Any]:
    """构造一条 lead 字典。"""
    return {
        "id": f"{PLATFORM}_{job_id}",
        "platform": PLATFORM,
        "source_url": source_url,
        "title": title,
        "publisher": publisher,
        "description": description,
        "budget_signal": budget_signal or None,
        "salary_raw": salary_raw,
        "extra": extra,
        "published_at": published_at,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
    }


# 首次爬取条数（无历史时）
FIRST_RUN_MAX_LEADS = 100
# 增量时每类搜索拉取条数（用于筛出「上次至今」的增量）
INCREMENTAL_PER_QUERY_ITEMS = 40
# 首次爬取时每轮 Apify 请求条数（多拉一些以便筛出足够「时薪≥30 或 固定≥1000」的线索，Actor 单页约 50）
FIRST_RUN_ITEMS_PER_REQUEST = 50
# 预算筛选：只保留「时薪≥30 或 固定≥1000」的线索（与 Apify 请求参数一致，本地二次校验）
HOURLY_RATE_MIN_USD = 30
FIXED_PRICE_MIN_USD = 1000


def _meets_budget_filter(item: dict[str, Any]) -> bool:
    """Apify 返回的 item 是否满足预算条件：时薪≥30 或 固定≥1000。无预算字段时保留（信任 Apify 已过滤）。"""
    hourly_min = item.get("budget_hourly_min_usd")
    if hourly_min is not None:
        try:
            if float(hourly_min) >= HOURLY_RATE_MIN_USD:
                return True
        except (TypeError, ValueError):
            pass
    total = item.get("budget_total_usd")
    if total is not None:
        try:
            if float(total) >= FIXED_PRICE_MIN_USD:
                return True
        except (TypeError, ValueError):
            pass
    # 无任何预算字段时保留，避免误删（Apify 已按 hourlyRateMin/fixedPriceMin 请求）
    if hourly_min is None and total is None:
        return True
    return False


def crawl_upwork(dry_run: bool = False, max_leads: int | None = None) -> tuple[int, list[dict[str, Any]]]:
    """
    执行 Upwork 抓取（仅 Apify 模式）。
    - 只保留「时薪≥30 或 固定≥1000」的线索：拿到 Apify 结果后先做本地预算校验，通过才入库；首次爬取以「装满 cap 条有效线索」为目标，持续拉取直到满或数据用完。
    - 首次（无 last_crawl_at）：目标 100 条有效线索，每轮请求较多条数，校验后去重，装满 100 才停止。
    - 之后每次：只保留「发布时间在上次爬取～本次爬取之间」的增量，去重后入库并更新 last_crawl_at。
    需在 .env 中配置 APIFY_API_TOKEN。
    max_leads: 仅首次生效时作为目标条数（默认 100）；增量时不限制条数。
    返回 (本次条数, 线索列表)。
    """
    apify_token = (os.environ.get("APIFY_API_TOKEN") or "").strip()
    if not apify_token:
        logger.warning("未配置 APIFY_API_TOKEN，跳过 Upwork 抓取。请在 .env 中配置后重试。")
        return 0, []

    keywords = load_yaml("keywords.yaml")
    queries = (keywords.get("upwork") or {}).get("search_queries") or [
        "AI Short Drama",
        "AI Mini Series",
    ]
    sites = load_yaml("sites.yaml")
    site_config = (sites.get("upwork") or {}).copy()
    base_url = site_config.get("base_url", "https://www.upwork.com")

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.warning("未安装 apify-client，请执行: pip install apify-client")
        return 0, []

    init_db()
    last_iso = get_last_crawl_at(PLATFORM)
    is_first_run = last_iso is None
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    last_dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00")) if last_iso else None

    if is_first_run:
        cap = max_leads if max_leads is not None else FIRST_RUN_MAX_LEADS
        per_query = FIRST_RUN_ITEMS_PER_REQUEST
        logger.info(
            "使用 Apify 模式（Actor: %s），首次爬取，目标 %d 条有效线索（时薪≥30 或 固定≥1000），每轮请求 %d 条",
            APIFY_ACTOR_ID, cap, per_query,
        )
    else:
        cap = None
        per_query = INCREMENTAL_PER_QUERY_ITEMS
        logger.info("使用 Apify 模式（Actor: %s），增量爬取（发布时间 >= %s）", APIFY_ACTOR_ID, last_iso)

    all_leads = []
    seen = set()

    try:
        client = ApifyClient(apify_token)
        for i, q in enumerate(queries):
            if cap is not None and len(all_leads) >= cap:
                break
            for run_label, run_input in [
                (
                    "时薪≥30",
                    {
                        "searchQuery": q,
                        "maxItems": per_query,
                        "hourlyRateMin": 30,
                        "location": ["worldwide", ""],
                    },
                ),
                (
                    "固定≥1000",
                    {
                        "searchQuery": q,
                        "maxItems": per_query,
                        "fixedPriceMin": 1000,
                        "location": ["worldwide", ""],
                    },
                ),
            ]:
                if cap is not None and len(all_leads) >= cap:
                    break
                logger.info("Apify 搜索 (%d/%d): %s [%s]", i + 1, len(queries), q, run_label)
                run = client.actor(APIFY_ACTOR_ID).call(run_input=run_input)
                dataset_id = run.get("defaultDatasetId")
                if not dataset_id:
                    continue
                items = client.dataset(dataset_id).list_items().items
                for item in items:
                    if not _meets_budget_filter(item):
                        continue
                    lead = _lead_from_apify_item(item, base_url)
                    if not lead or lead["id"] in seen:
                        continue
                    seen.add(lead["id"])
                    if is_first_run:
                        all_leads.append(lead)
                        if cap is not None and len(all_leads) >= cap:
                            break
                    else:
                        pub_dt = _parse_published_at(lead.get("published_at"))
                        if pub_dt is None or (last_dt <= pub_dt <= now_dt):
                            all_leads.append(lead)
                if cap is not None and len(all_leads) >= cap:
                    break
            if cap is not None and len(all_leads) >= cap:
                break
        logger.info(
            "Apify 多关键词共返回去重且满足预算的 %d 条%s",
            len(all_leads),
            "（已满目标）" if (cap is not None and len(all_leads) >= cap) else "",
        )
    except Exception as e:
        logger.exception("Apify 运行失败: %s", e)
        all_leads = []

    out = all_leads[:cap] if cap is not None else all_leads
    if dry_run:
        logger.info("Dry run: would save %d leads", len(out))
        return len(out), out
    if not out:
        return 0, []
    return len(out), out
