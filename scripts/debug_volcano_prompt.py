#!/usr/bin/env python3
"""
Prompt 调试：用指定英文职位描述调用火山引擎摘要，查看返回结果。
用法（项目根目录）：python scripts/debug_volcano_prompt.py
需配置 .env 中 VOLCANO_API_KEY 或 ARK_API_KEY。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 你提供的调试用职位描述（来自 leads.db 风格内容）
DEBUG_DESCRIPTION = """We're looking for a Subject Matter Expert (SME) to support ongoing maintenance of an AI course for our EdTech company, Springboard. Start: April (ahead of a May cohort launch) Ideal candidate: Currently working in an AI or AI-adjacent role (clear subject-matter expertise) Experience creating AI tool demos, preferably as part of current work Comfortable evaluating emerging AI tools and recommending whether our course should include tools beyond the commonly referenced ones Able to share 1-2 work samples (AI demos, tutorials, or similar) Location: US-based This is a maintenance-focused SME role, helping keep course content and demos accurate, relevant, and aligned with the evolving AI tooling landscape."""


def main():
    from src.gemini_summary import summarize_description

    print("=" * 60)
    print("输入描述（送火山的原文）:")
    print("=" * 60)
    print(DEBUG_DESCRIPTION)
    print()
    print("=" * 60)
    print("调用火山引擎摘要...")
    print("=" * 60)

    result = summarize_description(DEBUG_DESCRIPTION)

    print()
    print("=" * 60)
    print("火山返回的总结结果（≤100 字）:")
    print("=" * 60)
    if result:
        print(result)
        print()
        print(f"字数: {len(result)}")
    else:
        print("(无返回或调用失败，请查看上方日志)")


if __name__ == "__main__":
    main()
