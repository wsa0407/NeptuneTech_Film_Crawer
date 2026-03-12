#!/usr/bin/env python3
"""
导出 CRM 中状态为「跟进中」的线索为 Excel 表格。
用法（项目根目录）：python scripts/export_following_to_excel.py
输出文件：data/leads_following_YYYYMMDD_HHMM.xlsx
"""
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


def main():
    from src.storage.store import list_leads, get_follow_up

    # 获取所有「跟进中」线索（分页取满）
    limit = 2000
    all_leads = []
    offset = 0
    while True:
        leads, total = list_leads(status_filter="following", limit=limit, offset=offset)
        all_leads.extend(leads)
        if len(leads) < limit or len(all_leads) >= total:
            break
        offset += limit

    if not all_leads:
        print("没有状态为「跟进中」的线索")
        return

    # 为每条补充跟进备注与更新时间
    for lead in all_leads:
        fu = get_follow_up(lead["id"])
        lead["_notes"] = (fu["notes"] or "") if fu else ""
        lead["_updated_at"] = (fu["updated_at"] or "") if fu else ""
        lead["_core_summary"] = (lead.get("extra") or {}).get("core_summary") or ""

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment
    except ImportError:
        print("请先安装 openpyxl：pip install openpyxl")
        sys.exit(1)

    wb = Workbook()
    ws = wb.active
    ws.title = "跟进中"

    # 表头
    headers = [
        "ID", "平台", "标题", "发布方", "预算", "发布时间", "抓取时间",
        "核心描述", "跟进备注", "备注更新时间", "直达链接",
    ]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True)

    for row_idx, lead in enumerate(all_leads, 2):
        ws.cell(row=row_idx, column=1, value=lead.get("id") or "")
        ws.cell(row=row_idx, column=2, value=lead.get("platform") or "")
        ws.cell(row=row_idx, column=3, value=lead.get("title") or "")
        ws.cell(row=row_idx, column=4, value=lead.get("publisher") or "")
        ws.cell(row=row_idx, column=5, value=lead.get("budget_signal") or lead.get("salary_raw") or "")
        ws.cell(row=row_idx, column=6, value=lead.get("published_at") or "")
        ws.cell(row=row_idx, column=7, value=lead.get("crawled_at") or "")
        ws.cell(row=row_idx, column=8, value=lead.get("_core_summary") or "")
        ws.cell(row=row_idx, column=9, value=lead.get("_notes") or "")
        ws.cell(row=row_idx, column=10, value=lead.get("_updated_at") or "")
        ws.cell(row=row_idx, column=11, value=lead.get("source_url") or "")

    # 列宽
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 50
    ws.column_dimensions["D"].width = 20
    ws.column_dimensions["E"].width = 14
    ws.column_dimensions["F"].width = 22
    ws.column_dimensions["G"].width = 22
    ws.column_dimensions["H"].width = 50
    ws.column_dimensions["I"].width = 40
    ws.column_dimensions["J"].width = 22
    ws.column_dimensions["K"].width = 50

    out_dir = ROOT / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = out_dir / f"leads_following_{ts}.xlsx"
    wb.save(out_path)
    print(f"已导出 {len(all_leads)} 条「跟进中」线索到：{out_path}")


if __name__ == "__main__":
    main()
