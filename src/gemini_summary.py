"""
摘要模块（PRD v2）：将职位完整描述总结为 100 字以内的中文，用于 Telegram 卡片「核心描述」。
使用 OpenAI 兼容客户端调用火山引擎方舟 Responses API；需在 .env 中配置 ARK_API_KEY（或 VOLCANO_API_KEY）、可选 VOLCANO_MODEL。示例：base_url=https://ark.cn-beijing.volces.com/api/v3，model=doubao-seed-2-0-pro-260215。
未配置或调用失败时返回 None，由调用方回退为描述前 30 字。
"""
import logging
import os
import re

from openai import OpenAI

logger = logging.getLogger(__name__)

# 单条描述最大送入字数，控制 token
MAX_DESCRIPTION_CHARS = 6000
# 摘要最大中文字数（含标点）
MAX_SUMMARY_CHARS = 200

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "deepseek-v3-2-251201"

SYSTEM_INSTRUCTION = """你是一个招聘需求总结助手。请将用户给出的英文职位描述总结为一段中文，控制在250字左右（含标点），给出关键信息，如：岗位描述、候选人要求、是否需要作品集等。只输出这一段中文总结，不要列表、不要标题、不要给出思考过程，请直接给出通顺的总结结果。"""

USER_PROMPT_TEMPLATE = """请将以下职位描述总结为200字左右的中文：

---
%s
---
只输出一段中文总结，不要有思考过程和内容。"""


def _truncate_to_chars(s: str, max_chars: int) -> str:
    """按字符数截断（中文、英文均算 1 字符）。"""
    if not s or len(s) <= max_chars:
        return (s or "").strip()
    return s[:max_chars].strip()


def _truncate_at_sentence(s: str, max_chars: int) -> str:
    """在 max_chars 内尽量保留完整句子，避免截断到半句。"""
    s = (s or "").strip()
    if not s or len(s) <= max_chars:
        return s
    # 在限制内找最后一个句号、问号、感叹号或分号
    segment = s[: max_chars + 1]
    for sep in ("。", "！", "？", "；", "."):
        idx = segment.rfind(sep)
        if idx != -1 and idx > 0:
            return segment[: idx + 1].strip()
    # 没有句末标点则按原逻辑截断
    return s[:max_chars].strip()


def _get_api_key() -> str:
    """ARK_API_KEY 或 VOLCANO_API_KEY，优先前者（与火山引擎文档一致）。"""
    return (
        (os.environ.get("ARK_API_KEY") or os.environ.get("VOLCANO_API_KEY") or "").strip()
    )


REASONING_PREFIXES = (
    "对，再改改：", "对，数下字数", "哦对，整理顺一点：", "然后缩一缩，控制字数。",
    "调整下：", "我看看，调整下：", "大概：", "等下，再调得准一点",
    "用户现在需要把这个", "首先，", "然后整理得通顺，",
)

def _strip_reasoning_prefix(t: str) -> str:
    """去掉句首常见思考前缀，保留纯总结。"""
    t = (t or "").strip()
    for prefix in REASONING_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
            break
    for p in ("对，", "有没有", "我看看", "数一下："):
        if t.startswith(p):
            t = t[len(p) :].strip()
            break
    return t.strip()

def _take_final_summary_if_reasoning(s: str) -> str:
    """若模型返回含思考过程，取最终总结句并去掉句首思考前缀（≤MAX_SUMMARY_CHARS）。"""
    if not s or len(s) <= MAX_SUMMARY_CHARS:
        return _strip_reasoning_prefix(s)

    for sep in ("调整下：", "我看看，调整下：", "大概：", "哦对，整理顺一点：", "对，再改改："):
        if sep in s:
            idx = s.rfind(sep)
            tail = s[idx + len(sep) :].strip()
            if not tail:
                continue
            tail = _strip_reasoning_prefix(tail)
            if len(tail) <= MAX_SUMMARY_CHARS:
                return tail
            parts = [_strip_reasoning_prefix(p) for p in tail.split("。") if p.strip()]
            for p in parts:
                if not p or p.startswith(("对，", "有没有", "我看看", "数一下")):
                    continue
                cand = (p + "。").strip()
                if len(cand) <= MAX_SUMMARY_CHARS:
                    return cand
            if parts:
                return _truncate_to_chars(parts[0] + "。" if parts[0] else tail, MAX_SUMMARY_CHARS)
            return _truncate_to_chars(tail, MAX_SUMMARY_CHARS)

    parts = [_strip_reasoning_prefix(p) for p in s.split("。") if p.strip()]
    if len(parts) >= 2 and len(parts[-1]) <= MAX_SUMMARY_CHARS:
        return parts[-1] + "。"
    return _truncate_to_chars(_strip_reasoning_prefix(s), MAX_SUMMARY_CHARS)


def _get_text_from_part(part) -> str:
    """从 content 的单个 part（可能是 output_text、带 text 的对象或 dict）取文本。"""
    if part is None:
        return ""
    if isinstance(part, dict):
        return (part.get("text") or "").strip()
    t = getattr(part, "text", None)
    if t and str(t).strip():
        return str(t).strip()
    if getattr(part, "type", None) == "output_text" and getattr(part, "text", None):
        return str(part.text).strip()
    return ""


def _extract_text_from_response(response) -> str:
    """从 response 中只提取火山引擎返回的「摘要文案」；不包含爬虫的完整描述（完整描述仍在 lead["description"]）。"""
    text = ""
    # 1) 顶层 output_text（部分兼容形态）
    if getattr(response, "output_text", None):
        text = (response.output_text or "").strip()
    # 2) output 为 list：先试 output[].summary（方舟部分模型返回在此），再遍历 output[].content[].text
    if not text and getattr(response, "output", None):
        output = response.output
        if isinstance(output, list):
            for item in output:
                summary_val = getattr(item, "summary", None) or (item.get("summary") if isinstance(item, dict) else None)
                if isinstance(summary_val, str) and summary_val.strip():
                    text = summary_val.strip()
                    break
                if isinstance(summary_val, list):
                    for block in summary_val:
                        block_text = _get_text_from_part(block) or (block.get("text") if isinstance(block, dict) else "")
                        if isinstance(block_text, str) and block_text.strip():
                            text = (text + " " + block_text.strip()).strip()
                    if text:
                        text = _take_final_summary_if_reasoning(text)
                        break
                content = (
                    getattr(item, "content", None)
                    or (item.get("content") if isinstance(item, dict) else None)
                    or []
                )
                for part in content:
                    part_text = _get_text_from_part(part)
                    if part_text:
                        text = (text + " " + part_text).strip()
                if text:
                    break
    # 3) output 为 dict：方舟可能返回 output.output_items 或 output.output_text
    if not text and getattr(response, "output", None):
        output = response.output
        if isinstance(output, dict):
            direct = output.get("output_text") or output.get("text")
            if isinstance(direct, str) and direct.strip():
                text = direct.strip()
            if not text:
                items = output.get("output_items") or output.get("output") or []
                for item in items if isinstance(items, list) else []:
                    content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict):
                                part_text = (part.get("text") or "").strip()
                            else:
                                part_text = _get_text_from_part(part)
                            if part_text:
                                text = (text + " " + part_text).strip()
                    if text:
                        break
    # 4) 兜底：output[0].content[0].text（含 type 不匹配时仍取 text）
    if not text and getattr(response, "output", None):
        output = response.output or []
        if isinstance(output, list) and output:
            first = output[0]
            content = getattr(first, "content", None) or (first.get("content") if isinstance(first, dict) else None)
            if isinstance(content, list) and content:
                first_part = content[0]
                if isinstance(first_part, dict):
                    text = (first_part.get("text") or "").strip()
                else:
                    text = _get_text_from_part(first_part)
    return text


def summarize_description(description: str | None) -> str | None:
    """
    将职位完整描述总结为 50 字以内的中文（调用火山引擎 Doubao）。
    - description: 爬虫返回的完整职位描述全文（送入 API 的即此全文，仅按 MAX_DESCRIPTION_CHARS 截断）。
    - 从 API response 中只读取模型生成的摘要，不读取、不返回爬虫原文。
    返回：总结后的中文字符串（≤100 字），失败或未配置时返回 None。
    """
    api_key = _get_api_key()
    if not api_key:
        return None
    # 1）发送给火山的是爬虫返回的完整描述（过长时按字数截断）
    crawler_full_description = (description or "").strip()
    if len(crawler_full_description) < 10:
        return None
    crawler_full_description = _truncate_to_chars(
        crawler_full_description, MAX_DESCRIPTION_CHARS
    )
    user_content = USER_PROMPT_TEMPLATE % crawler_full_description
    model = (os.environ.get("VOLCANO_MODEL") or "").strip() or DEFAULT_MODEL
    full_prompt = f"{SYSTEM_INSTRUCTION}\n\n{user_content}"

    logger.info(
        "火山摘要-送入描述(%d字): %s",
        len(crawler_full_description),
        crawler_full_description[:150] + ("…" if len(crawler_full_description) > 150 else ""),
    )
    try:
        client = OpenAI(base_url=ARK_BASE_URL, api_key=api_key)
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": full_prompt}],
                }
            ],
            max_output_tokens=400,
        )
    except Exception as e:
        logger.warning("火山引擎摘要失败，将使用描述前30字: %s", e)
        return None

    # 从 response 里只取火山返回的摘要文案，不是爬虫原文
    model_summary = _extract_text_from_response(response)
    if not model_summary:
        out_preview = ""
        if getattr(response, "output", None) is not None:
            o = response.output
            if isinstance(o, list):
                out_preview = "list len=%d" % len(o)
                if o and hasattr(o[0], "__dict__"):
                    out_preview += " first_keys=%s" % (list(getattr(o[0], "__dict__", {}).keys())[:8],)
            elif isinstance(o, dict):
                out_preview = "dict keys=%s" % (list(o.keys())[:10],)
        logger.warning(
            "火山摘要-未能从 response 解析出文本，将回退为描述前30字。response=%s output=%s",
            type(response).__name__,
            out_preview,
        )
        return None
    model_summary = re.sub(r"\s+", " ", model_summary)
    result = _truncate_at_sentence(model_summary, MAX_SUMMARY_CHARS) or None
    if result:
        result = _strip_reasoning_prefix(result) or result
        logger.info("火山摘要-总结结果: %s", result)
    return result


def enrich_leads_with_summary(leads: list[dict]) -> None:
    """
    就地为每条 lead 补充 core_summary（若已配置 API 且描述非空）。
    - 2）逐条对应：每条 lead 用本条 lead 的 description 调用一次火山，一一对应总结。
    - 3）不替代原文：只写入 lead["core_summary"]；绝不修改 lead["description"]（爬虫完整文案保留）。
    """
    if not leads:
        return
    for lead in leads:
        crawler_description = (lead.get("description") or "").strip()
        if not crawler_description or len(crawler_description) < 10:
            continue
        # 每条 lead 独立调用一次，逐条对应
        summary = summarize_description(crawler_description)
        if summary:
            lead["core_summary"] = summary
            extra = lead.get("extra") or {}
            extra["core_summary"] = summary
            lead["extra"] = extra
        else:
            logger.info(
                "火山摘要-本条未写入 core_summary，卡片将使用描述前30字。title=%s",
                (lead.get("title") or "")[:50],
            )
