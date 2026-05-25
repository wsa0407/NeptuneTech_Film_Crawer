"""
Upwork 定向采集器（Apify 模式）。
使用 Apify Actor YdYsB7rsRY0EUb1lP：按发布时间范围（每次运行前由用户输入）、
关键词「AI-Generated Video」匹配 Skills、预算时薪≥30 或 固定≥1200 抓取并入库。
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
APIFY_ACTOR_ID = "YdYsB7rsRY0EUb1lP"


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
    """详情页直连 URL：https://www.upwork.com/jobs/~02{uid}（与 Apify 返回格式一致）"""
    base_url = base_url.rstrip("/")
    return f"{base_url}/jobs/~02{job_id}"


def _lead_from_apify_item(item: dict[str, Any], base_url: str) -> dict[str, Any] | None:
    """将 Apify Actor 输出的一条 item 转为 lead。兼容 snake_case 与 camelCase。"""
    url = (item.get("url") or item.get("jobUrl") or item.get("link") or "").strip()
    # 新 Actor：优先用 Uid 作为唯一标识，落库 id 必须为 upwork_{Uid}
    uid_raw = item.get("Uid") or item.get("uid") or item.get("UID")
    uid = str(uid_raw).strip() if uid_raw is not None else ""
    job_id = uid or (item.get("job_id") or item.get("jobId") or "").strip() or (_extract_job_id_from_url(url) if url else "")
    if not job_id:
        job_id = (str(item.get("id")).strip() if item.get("id") is not None else "")
    title = (item.get("title") or item.get("jobTitle") or item.get("name") or "").strip()
    title = _strip_html(title)
    if not title or len(title) < 2:
        return None
    description = (
        item.get("description_text")
        or item.get("descriptionText")
        or item.get("description")
        or item.get("snippet")
        or item.get("body")
        or ""
    )
    if isinstance(description, str):
        description = _strip_html(description, preserve_newlines=True)
    else:
        description = ""
    # 预算：新 Actor 可能返回 budget.fixedBudget 与 budget.hourlyRate{min,max}
    hourly_str = ""
    fixed_str = ""
    budget_obj = item.get("budget") if isinstance(item.get("budget"), dict) else {}
    fixed_budget = budget_obj.get("fixedBudget") if isinstance(budget_obj, dict) else None
    hourly_rate = budget_obj.get("hourlyRate") if isinstance(budget_obj, dict) else None
    if isinstance(hourly_rate, dict):
        lo = hourly_rate.get("min")
        hi = hourly_rate.get("max")
    else:
        lo = item.get("budget_hourly_min_usd") or item.get("budgetHourlyMinUsd")
        hi = item.get("budget_hourly_max_usd") or item.get("budgetHourlyMaxUsd")
    if fixed_budget is None:
        fixed_budget = item.get("budget_total_usd") or item.get("budgetTotalUsd") or item.get("fixedPrice")
    if fixed_budget is not None:
        fixed_str = str(fixed_budget).strip()
    if lo is not None or hi is not None:
        lo_s = str(lo).strip() if lo is not None else ""
        hi_s = str(hi).strip() if hi is not None else ""
        if lo_s and hi_s:
            hourly_str = f"{lo_s}-{hi_s}"
        else:
            hourly_str = lo_s or hi_s or ""
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
    if fixed_str:
        parts.append(f"固定 {fixed_str}")
    elif hourly_str:
        parts.append(f"时薪 {hourly_str}")
    budget_str = " | ".join(parts) if parts else ""
    # 直达链接：优先使用接口返回的链接
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
    publisher_raw = item.get("clientName") or item.get("client")
    if isinstance(publisher_raw, dict):
        publisher = (publisher_raw.get("name") or publisher_raw.get("title") or "").strip() or "—"
    else:
        publisher = (str(publisher_raw).strip() if publisher_raw else "") or "—"
    return _make_lead(
        job_id=job_id or str(abs(hash(url)) % 10**12),
        title=title,
        source_url=source_url,
        publisher=publisher,
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


# 单次运行默认拉取条数
DEFAULT_MAX_LEADS = 100
# 预算筛选：只保留「时薪≥30 或 固定≥1000」的线索（与 Apify 请求参数一致，本地二次校验）
HOURLY_RATE_MIN_USD = 30
FIXED_PRICE_MIN_USD = 1000


def _meets_budget_filter(item: dict[str, Any]) -> bool:
    """Apify 返回的 item 是否满足预算条件：时薪≥30 或 固定≥1000。无预算字段时保留（信任 Apify 已过滤）。"""
    hourly_min = item.get("budget_hourly_min_usd") or item.get("budgetHourlyMinUsd")
    if hourly_min is not None:
        try:
            if float(hourly_min) >= HOURLY_RATE_MIN_USD:
                return True
        except (TypeError, ValueError):
            pass
    total = item.get("budget_total_usd") or item.get("budgetTotalUsd") or item.get("fixedPrice")
    if total is not None:
        try:
            if float(total) >= FIXED_PRICE_MIN_USD:
                return True
        except (TypeError, ValueError):
            pass
    if hourly_min is None and total is None:
        return True
    return False


def _build_run_input(from_date: str, to_date: str, limit: int) -> dict[str, Any]:
    """构建新 Actor (YdYsB7rsRY0EUb1lP) 的 run_input（按用户提供的字段集合）。"""
    return {
        "addons.enableClientActivity": False,
        "addons.enableClientDetails": False,
        "addons.enableJobAttachments": False,
        "budget.allowUnspecifiedBudget": False,
        "budget.fixedPrice.min": "1000",
        "budget.hourlyRate.min": "30",
        "budget.minClientHireRate": 0,
        "budget.noAvgHourlyRatePaid": False,
        "budget.noHireRate": False,
        "budget.onlyContractToHire": False,
        "client.includeWithNoFeedback": False,
        "client.paymentMethodVerified": False,
        "client.phoneNumberVerified": False,
        "excludeKeywords.matchDescription": True,
        "excludeKeywords.matchSkills": True,
        "excludeKeywords.matchTitle": True,
        "fromDate": from_date,
        "includeKeywords.keywords": ["AI-Generated Video"],
        "includeKeywords.matchDescription": False,
        "includeKeywords.matchSkills": True,
        "includeKeywords.matchTitle": False,
        "limit": limit,
        "notifications.limit": 3,
        "notifications.shouldSendRunMetadata": True,
        "toDate": to_date,
        "vendor.excludeWithQuestions": False,
        "vendor.includeFeatured": False,
        "vendor.includeWithoutCountryPreference": False,
    }


def crawl_upwork(
    from_date: str,
    to_date: str,
    dry_run: bool = False,
    max_leads: int | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    """
    执行 Upwork 抓取（新 Apify Actor YdYsB7rsRY0EUb1lP）。
    - 发布时间范围：由调用方传入 from_date / to_date（每次爬虫前用户输入）。
    - 关键词：AI-Generated Video，匹配 Skills。
    - 预算：时薪≥30 或 固定≥1000，API 与本地双重过滤。
    返回 (本次条数, 线索列表)。
    """
    apify_token = (os.environ.get("APIFY_API_TOKEN") or "").strip()
    if not apify_token:
        logger.warning("未配置 APIFY_API_TOKEN，跳过 Upwork 抓取。请在 .env 中配置后重试。")
        return 0, []

    # limit 由 Apify 返回日期范围内符合筛选条件的结果（当前 limit=3000）
    limit = 3000
    run_input = _build_run_input(from_date, to_date, limit)

    sites = load_yaml("sites.yaml")
    site_config = (sites.get("upwork") or {}).copy()
    base_url = site_config.get("base_url", "https://www.upwork.com")

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.warning("未安装 apify-client，请执行: pip install apify-client")
        return 0, []

    init_db()
    logger.info(
        "Apify Actor %s：fromDate=%s toDate=%s limit=%d，关键词 AI-Generated Video (Skills)，时薪≥30 或 固定≥1000",
        APIFY_ACTOR_ID, from_date, to_date, limit,
    )

    all_leads = []
    seen = set()
    try:
        client = ApifyClient(apify_token)
        run = client.actor(APIFY_ACTOR_ID).call(run_input=run_input)
        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            logger.warning("Actor 未返回 defaultDatasetId")
            return 0, []
        items = list(client.dataset(dataset_id).iterate_items())
        first_item = items[0] if items else None
        for item in items:
            if not _meets_budget_filter(item):
                continue
            lead = _lead_from_apify_item(item, base_url)
            if not lead or lead["id"] in seen:
                continue
            seen.add(lead["id"])
            all_leads.append(lead)
        logger.info("Apify 返回去重且满足预算的 %d 条", len(all_leads))
        if items and not all_leads and first_item is not None:
            logger.warning(
                "Actor 返回 %d 条 item 但过滤后为 0，首条 item 的键供核对字段: %s",
                len(items),
                list(first_item.keys()) if isinstance(first_item, dict) else type(first_item).__name__,
            )
    except Exception as e:
        logger.exception("Apify 运行失败: %s", e)
        all_leads = []

    if dry_run:
        logger.info("Dry run: would save %d leads", len(all_leads))
        return len(all_leads), all_leads
    if not all_leads:
        return 0, []
    return len(all_leads), all_leads
