#!/usr/bin/env python3
"""
Demo：用一段固定文案模拟爬虫返回，调用火山引擎得到核心描述并打印。
用法：在项目根目录执行 python scripts/demo_volcano_summary.py
需配置 .env 中的 VOLCANO_API_KEY 或 ARK_API_KEY。
"""
import sys
from pathlib import Path

# 项目根
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

# 模拟爬虫返回的职位描述
DEMO_DESCRIPTION = r"""Summary
WHAT WE ARE BUILDING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Reflektive is the world's first Cognitive Clarity Engine — a premium AI app for high-performers, founders, and executives. Our brand sits at the intersection of luxury technology and human psychology. Think Apple meets Dior meets performance neuroscience.

We are creating a series of cinematic short-form brand films for Instagram Reels, TikTok, and YouTube Shorts. These are NOT talking-head edits. They are NOT influencer-style videos. They are visual stories — closer to a luxury car commercial or a high-end fragrance ad than anything you typically see on social media.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE AESTHETIC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Dark, neon-touched, high contrast. Slow motion and whip cuts used with complete intention. Color grading: deep, moody, nocturnal — midnight blues, warm ambers, clinical whites. No stock-looking filters. No bright cheery tones. No influencer energy whatsoever.

The subtitles ARE the content. They carry the coaching, the insight, the teaching. They are not an afterthought — they are designed into the frame. Typography must feel luxury and intentional, not templated.

Sound is 50% of the film. Music is provided by us for each video. Your job is to edit to the music with surgical precision — every cut lands on a beat, every silence is felt, every resolution is earned.

Reference aesthetic: BMW Films, Dior and Tom Ford fragrance commercials, Rolls Royce brand content, Apple product launches. We will provide a full visual reference folder on onboarding.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT EACH FILM LOOKS LIKE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Each film is 30–60 seconds. For every video, we provide:
• A complete shot-by-shot script with visual direction and subtitle text
• The full emotional arc and pacing structure
• The music track — a specific section of a provided song, edited to picture
• All Reflektive brand assets (UI mockups, logo, typography guidelines)

You provide:
• Premium stock footage sourcing that matches the visual direction exactly (we cover licensing costs via Artgrid, Storyblocks, or equivalent)
• Cinematic color grading — moody, intentional, consistent with our palette
• Music editing — cutting the provided track to sync perfectly with the visual arc, including the precise moment of silence and emotional resolution
• Subtitle integration that feels designed into the frame, not placed on top of it
• Pacing that builds tension, breaks it at the right moment, and resolves with emotional weight
• 9:16 vertical format, exported for IG Reels, TikTok, and YouTube Shorts

To give you a sense of the output: our first film opens on an extreme close-up of a dilating pupil, moves through rapid whip cuts of digital addiction and dopamine loops, drops into complete silence at the beat break, then resolves into warm steady light as the Reflektive interface appears. Every subtitle lands like a coaching insight. Every frame earns its place.

These films are published as organic content only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT WE NEED FROM YOU
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Non-negotiable:
• Mastery of Premiere Pro, After Effects, or DaVinci Resolve — not CapCut
• Strong stock footage sourcing ability — you know where to find the right shot, not just a close shot
• Music editing precision — you can cut a provided track, build to a drop, land on silence, and time a resolution
• Color grading that creates psychological mood, not just visual aesthetics
• Subtitle and typography placement that feels art-directed
• Ability to interpret an emotional brief and make creative decisions that serve it
• Turnaround: 72–96 hours per finished film

Strong bonus:
• Portfolio includes luxury brand, fashion, automotive, fragrance, or premium tech content
• You have edited to music before — not just placed music under footage
• Subtle motion graphics capability for UI and text animations

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PAID TEST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

We will commission one test film before committing to a retainer. You will receive:
• A complete shot-by-shot script and visual brief
• The music track with the specific section marked
• Our brand asset folder and visual references

You deliver one finished 45–60 second film.  If it meets the brief, we move to an ongoing retainer immediately. No lengthy back and forth — the brief does the work.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPENSATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ongoing retainer: 10–12 films per month for the right editor
This is a long-term creative partnership — we want one person who owns this, not a revolving door of freelancers

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TO APPLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Share 3–5 samples of your most cinematic or premium brand work — direct links only, no folders
2. Answer this question in 3–5 sentences: A 47-second film needs to build tension through rapid cuts, hit a moment of complete silence, then resolve into warmth and clarity. Walk me through the three most important editorial decisions you make to execute that arc.
3. Your preferred editing tool and why
4. Your rate per film and your monthly capacity

If your portfolio does not include premium or cinematic work, this is not the right project for you. Applications without portfolio links or without answering the creative question will not be reviewed.

We respond to every serious applicant within 48 hours."""


def _inspect_response(response):
    """打印 response.output 结构便于调试。"""
    out = getattr(response, "output", None)
    if not out or not isinstance(out, list) or not out:
        return
    item = out[0]
    if hasattr(item, "__dict__"):
        d = getattr(item, "__dict__", {})
    elif isinstance(item, dict):
        d = item
    else:
        d = {}
    for k in ["summary", "content", "type"]:
        if k in d:
            v = d[k]
            if isinstance(v, str) and len(v) > 200:
                print(f"  [{k}] (str len={len(v)}): {v[:200]}...")
            elif isinstance(v, list) and v and len(str(v)) > 300:
                print(f"  [{k}] (list len={len(v)}): first={v[0]!r}...")
            else:
                print(f"  [{k}]: {v!r}")

def main():
    from src.gemini_summary import summarize_description
    import os
    from openai import OpenAI

    print("=" * 60)
    print("Demo：模拟爬虫文案 → 火山引擎 → 核心描述")
    print("=" * 60)
    print("输入长度:", len(DEMO_DESCRIPTION), "字")
    print()

    # 仅当 DEMO_DEBUG=1 时打印 response 结构
    if os.environ.get("DEMO_DEBUG") == "1":
        api_key = (os.environ.get("VOLCANO_API_KEY") or os.environ.get("ARK_API_KEY") or "").strip()
        if api_key:
            from src.gemini_summary import (
                ARK_BASE_URL,
                DEFAULT_MODEL,
                SYSTEM_INSTRUCTION,
                USER_PROMPT_TEMPLATE,
                _truncate_to_chars,
                MAX_DESCRIPTION_CHARS,
            )
            raw = _truncate_to_chars(DEMO_DESCRIPTION.strip(), MAX_DESCRIPTION_CHARS)
            full_prompt = f"{SYSTEM_INSTRUCTION}\n\n{USER_PROMPT_TEMPLATE % raw}"
            client = OpenAI(base_url=ARK_BASE_URL, api_key=api_key)
            resp = client.responses.create(
                model=os.environ.get("VOLCANO_MODEL", "").strip() or DEFAULT_MODEL,
                input=[{"role": "user", "content": [{"type": "input_text", "text": full_prompt}]}],
                max_output_tokens=200,
            )
            print("Response output[0] 结构:")
            _inspect_response(resp)
            print()

    core_summary = summarize_description(DEMO_DESCRIPTION)

    print()
    print("=" * 60)
    if core_summary:
        print("【核心描述】（火山返回，≤100 字中文）:")
        print(core_summary)
        print("字数:", len(core_summary))
    else:
        print("【核心描述】未得到（API 未配置或解析失败，将回退为描述前30字）")
        fallback = (DEMO_DESCRIPTION or "")[:30]
        print("回退内容（前30字）:", fallback)
    print("=" * 60)


if __name__ == "__main__":
    main()
