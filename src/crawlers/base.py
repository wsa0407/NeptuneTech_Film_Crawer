"""
Base crawler: 随机延迟、配置加载、代理与环境变量。
"""
import os
import random
import time
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

# 项目根目录（crawler/）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def random_delay(min_sec: float = 5, max_sec: float = 15) -> None:
    """请求间随机延迟，模拟人类行为。"""
    time.sleep(random.uniform(min_sec, max_sec))


def get_proxy() -> dict[str, str] | None:
    """从环境变量读取代理，供 Playwright 使用。"""
    url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if not url:
        return None
    return {"server": url}


def get_data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
