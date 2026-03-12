"""
测试 Telegram Bot 是否能成功发消息。
若 .env 中未填 TELEGRAM_CHAT_ID，会尝试从 getUpdates 取最近一次聊天的 chat_id 并发送测试消息。
"""
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api.telegram.org/bot"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


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
        return True
    except Exception as e:
        print("写入 .env 失败:", e)
        return False


def get_updates(token: str) -> dict:
    url = f"{BASE}{token}/getUpdates"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as r:
        import json
        return json.loads(r.read().decode())


def send_message(token: str, chat_id: str, text: str) -> bool:
    url = f"{BASE}{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.getcode() == 200
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print("API 错误:", e.code, body[:300])
        return False


def main():
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

    if not token:
        print("未配置 TELEGRAM_BOT_TOKEN，请在 .env 中填写")
        return 1

    if not chat_id:
        print("未配置 TELEGRAM_CHAT_ID，尝试从 getUpdates 获取...")
        from_get_updates = True
        try:
            data = get_updates(token)
            results = data.get("result") or []
            for u in reversed(results):
                cid = (u.get("message") or u.get("channel_post") or {}).get("chat", {}).get("id")
                if cid is not None:
                    chat_id = str(cid)
                    print(f"从 getUpdates 得到 chat_id: {chat_id}")
                    break
            if not chat_id:
                print("getUpdates 中无聊天记录。请先给 Bot 发一条任意消息，再重新运行本脚本。")
                return 1
        except Exception as e:
            print("getUpdates 失败:", e)
            return 1
    else:
        from_get_updates = False

    text = "NepTune Crawler 测试：Bot 可正常发消息。"
    if send_message(token, chat_id, text):
        print("已发送测试消息到 Telegram。")
        if from_get_updates and _save_chat_id_to_env(chat_id):
            print("已将该 chat_id 写入 .env，之后运行爬虫时会自动推送到 Telegram。")
        return 0
    print("发送失败，请检查 token 与 chat_id。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
