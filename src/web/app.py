"""
V3 线索收录网站：登录、列表、筛选、详情、跟进（状态/备注）。
从项目根运行：python -m src.web.app 或 flask --app src.web.app run
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 保证从项目根可执行
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from markupsafe import Markup
from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from src.storage.store import (
    init_db,
    get_lead_by_id,
    list_leads,
    get_follow_up,
    set_follow_up,
)

# 默认登录账号（PRD）
DEFAULT_USER = os.environ.get("WEB_LOGIN_USER", "Sylicora")
DEFAULT_PASSWORD = os.environ.get("WEB_LOGIN_PASSWORD", "JustGetItDone")
SECRET_KEY = os.environ.get("WEB_SECRET_KEY", "nep-tune-v3-secret-change-in-prod")

STATUS_CHOICES = [
    ("pending", "待处理"),
    ("following", "跟进中"),
    ("converted", "已转化"),
    ("ignored", "已忽略"),
]

# 选择「已忽略」时弹窗中的原因枚举（待处理 / 跟进中页）
IGNORED_REASON_CHOICES = [
    ("mismatch_me", "不满足我方需求"),
    ("mismatch_user", "不满足用户需求"),
    ("offline", "岗位已下线"),
]

# 分区导航： (路由名, 显示名, 状态筛选, 是否可编辑状态, 可选的下一状态列表)
# 状态与模块一一对应：pending→待处理, following→跟进中, converted→已转化, ignored→已忽略；
# list_leads(status_filter=section_status_filter) 只显示该状态的线索；改状态后 save_follow_up 会跳转到对应模块。
NAV_SECTIONS = [
    ("overview", "线索总览", None, False, None),       # 只读，无操作列
    ("pending", "待处理", "pending", True, ["pending", "following", "ignored"]),
    ("following", "跟进中", "following", True, ["following", "converted", "ignored"]),
    ("converted", "已转化", "converted", False, None),
    ("ignored", "已忽略", "ignored", False, None),
]

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


def require_login(f):
    from functools import wraps
    @wraps(f)
    def g(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return g


def _core_desc(lead):
    """与 Telegram 一致：优先 core_summary，否则描述前 30 字。"""
    extra = lead.get("extra") or {}
    s = extra.get("core_summary") or ""
    if s and str(s).strip():
        return str(s).strip()
    desc = (lead.get("description") or "").strip()
    return (desc[:30] + "…") if len(desc) > 30 else (desc or "—")


def _format_time(iso_str):
    if not iso_str or not str(iso_str).strip():
        return "—"
    raw = str(iso_str).strip()
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
            return "1小时内"
        if delta < timedelta(hours=24):
            return f"{int(delta.total_seconds() // 3600)}小时前"
        if delta < timedelta(days=7):
            return f"{delta.days}天前"
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return raw[:16] if len(raw) > 16 else raw


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = (request.form.get("username") or "").strip()
        pw = request.form.get("password") or ""
        if user == DEFAULT_USER and pw == DEFAULT_PASSWORD:
            session["logged_in"] = True
            session["username"] = user
            next_url = request.args.get("next") or url_for("overview")
            return redirect(next_url)
        return render_template("login.html", error="账号或密码错误")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _list_view(section_key: str):
    """共用列表逻辑：section_key 为 overview / pending / following / converted / ignored。"""
    section = next((s for s in NAV_SECTIONS if s[0] == section_key), NAV_SECTIONS[0])
    _, section_title, section_status_filter, can_edit_status, allowed_statuses = section
    date_range = request.args.get("date") or "all"
    page = max(1, int(request.args.get("page") or 1))
    per_page = 15
    offset = (page - 1) * per_page
    # 线索总览页：状态、关键词从请求参数取；其余页用分区固定状态，无关键词
    if section_key == "overview":
        status_filter = request.args.get("status") or None
        filter_status = request.args.get("status") or ""
        search = request.args.get("q") or None
        filter_q = request.args.get("q") or ""
    else:
        status_filter = section_status_filter
        filter_status = ""
        search = None
        filter_q = ""

    published_from = published_to = None
    if date_range == "today":
        from datetime import date
        today = date.today().isoformat()
        # 用日期起止，兼容 DB 里只存 "YYYY-MM-DD" 的情况
        published_from = today
        published_to = today + "T23:59:59.999"
    elif date_range == "7d":
        d = datetime.now(timezone.utc) - timedelta(days=7)
        published_from = d.strftime("%Y-%m-%dT%H:%M:%S")
    elif date_range == "30d":
        d = datetime.now(timezone.utc) - timedelta(days=30)
        published_from = d.strftime("%Y-%m-%dT%H:%M:%S")

    init_db()
    leads, total = list_leads(
        platform=None,
        published_from=published_from,
        published_to=published_to,
        search=search,
        status_filter=status_filter,
        limit=per_page,
        offset=offset,
        order_by="published_at" if section_key == "overview" else "crawled_at",
        order_dir="desc",
    )
    for lead in leads:
        lead["core_desc"] = _core_desc(lead)
        lead["published_fmt"] = _format_time(lead.get("published_at"))
        lead["crawled_fmt"] = _format_time(lead.get("crawled_at"))
        if lead.get("title"):
            lead["title"] = Markup(lead["title"])
        fu = get_follow_up(lead["id"])
        lead["status"] = fu["status"] if fu else "pending"
        lead["status_label"] = dict(STATUS_CHOICES).get(lead["status"], lead["status"])
        lead["follow_up_notes"] = (fu["notes"] or "") if fu else ""

    total_pages = (total + per_page - 1) // per_page if total else 1
    # 翻页用的基础查询参数（不含 page），用于上一页/下一页/页码链接
    base_query = {"date": date_range}
    if section_key == "overview":
        if filter_status:
            base_query["status"] = filter_status
        if filter_q:
            base_query["q"] = filter_q
    # 页码列表：当前页前后各 2 页，不足的补全
    pagination_start = max(1, page - 2)
    pagination_end = min(total_pages, page + 2)
    if pagination_end - pagination_start < 4:
        if pagination_start == 1:
            pagination_end = min(total_pages, pagination_start + 4)
        else:
            pagination_start = max(1, pagination_end - 4)
    pagination_pages = list(range(pagination_start, pagination_end + 1))
    list_query = {"page": page, **base_query}
    return_to_list = url_for(section_key, **list_query)
    first_url = url_for(section_key, **dict(base_query, page=1)) if page > 1 else None
    prev_url = url_for(section_key, **dict(base_query, page=page - 1)) if page > 1 else None
    next_url = url_for(section_key, **dict(base_query, page=page + 1)) if page < total_pages else None
    last_url = url_for(section_key, **dict(base_query, page=total_pages)) if page < total_pages else None
    page_urls = [(p, url_for(section_key, **dict(base_query, page=p))) for p in pagination_pages]
    status_choices_filtered = (
        [(v, l) for v, l in STATUS_CHOICES if v in allowed_statuses]
        if allowed_statuses
        else []
    )
    return render_template(
        "list.html",
        section_key=section_key,
        section_title=section_title,
        leads=leads,
        total=total,
        page=page,
        total_pages=total_pages,
        date_range=date_range,
        filter_status=filter_status,
        filter_q=filter_q,
        show_status_filter=(section_key == "overview"),
        show_keyword_search=(section_key == "overview"),
        nav_sections=NAV_SECTIONS,
        can_edit_status=can_edit_status,
        show_actions=can_edit_status or (section_key == "ignored"),
        status_choices=status_choices_filtered if can_edit_status else STATUS_CHOICES,
        return_to_list=return_to_list,
        first_url=first_url,
        prev_url=prev_url,
        next_url=next_url,
        last_url=last_url,
        page_urls=page_urls,
        ignored_reason_choices=IGNORED_REASON_CHOICES,
    )


@app.route("/")
@require_login
def overview():
    """线索总览：只读，无状态操作，无操作列。"""
    return _list_view("overview")


@app.route("/pending")
@require_login
def pending():
    """待处理：可操作状态 -> 跟进中 或 已忽略。"""
    return _list_view("pending")


@app.route("/following")
@require_login
def following():
    """跟进中：可操作状态 -> 已转化 或 已忽略。"""
    return _list_view("following")


@app.route("/converted")
@require_login
def converted():
    """已转化：只读。"""
    return _list_view("converted")


@app.route("/ignored")
@require_login
def ignored():
    """已忽略：只读。"""
    return _list_view("ignored")


@app.route("/lead/<lead_id>")
@require_login
def lead_detail(lead_id):
    init_db()
    lead = get_lead_by_id(lead_id)
    if not lead:
        return "线索不存在", 404
    lead["core_desc"] = _core_desc(lead)
    # 详情页：核心描述 = 中文总结（完整描述区块已移除）
    extra = lead.get("extra") or {}
    summary = (extra.get("core_summary") or "").strip()
    lead["core_desc"] = summary if summary else "—"
    lead["published_fmt"] = _format_time(lead.get("published_at"))
    lead["crawled_fmt"] = _format_time(lead.get("crawled_at"))
    if lead.get("title"):
        lead["title"] = Markup(lead["title"])
    fu = get_follow_up(lead_id)
    lead["follow_up"] = fu or {"status": "pending", "notes": "", "updated_at": ""}
    lead["status_label"] = dict(STATUS_CHOICES).get(
        lead["follow_up"]["status"], lead["follow_up"]["status"]
    )
    return_to = request.args.get("next") or ""
    return render_template(
        "detail.html",
        lead=lead,
        status_choices=STATUS_CHOICES,
        ignored_reason_choices=IGNORED_REASON_CHOICES,
        return_to=return_to,
    )


@app.route("/lead/<lead_id>/follow-up", methods=["POST"])
@require_login
def save_follow_up(lead_id):
    if get_lead_by_id(lead_id) is None:
        return "线索不存在", 404
    status = request.form.get("status") or "pending"
    notes = request.form.get("notes") or ""
    set_follow_up(lead_id, status, notes)
    # 列表页改状态：跳回当前列表 URL，线索从当前页消失、页面不跳转模块；详情页改状态：跳回 next 所指的来路页面（模块）
    next_url = request.form.get("next") or ""
    if next_url and next_url.startswith("/") and "//" not in next_url:
        return redirect(next_url)
    return redirect(url_for("lead_detail", lead_id=lead_id))


def main():
    init_db()
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")


if __name__ == "__main__":
    main()
