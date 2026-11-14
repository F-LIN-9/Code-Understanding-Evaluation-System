# -*- coding: utf-8 -*-
"""全局配置：路径、数据库、大模型接口。

大模型接口兼容 OpenAI 的 /chat/completions 协议，可通过环境变量或
data/config.json 配置；未配置 key 时自动退化为本地规则引擎，系统仍可完整跑通。
"""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PKG_DIR = Path(__file__).resolve().parent
STATIC_DIR = PKG_DIR / "static"
SAMPLE_DIR = BASE_DIR / "samples"

DATA_DIR = Path(os.environ.get("CODEASSESS_DATA_DIR") or (BASE_DIR / "data"))
DB_PATH = DATA_DIR / "codeassess.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)

APP_NAME = "代码理解测评系统"
APP_SUB = "面向 AI 辅助编程 · 山东建筑大学开放实验项目"


def _env(*names, default=""):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


def llm_config():
    """读取大模型配置，环境变量优先于 data/config.json。"""
    conf = {
        "base_url": "",
        "api_key": "",
        "model": "gpt-4o-mini",
        "timeout": 60,
        "enabled": False,
    }
    cfg_file = DATA_DIR / "config.json"
    if cfg_file.exists():
        try:
            conf.update(json.loads(cfg_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    conf["base_url"] = _env("CODEASSESS_LLM_BASE", "OPENAI_BASE_URL",
                            default=conf.get("base_url", ""))
    conf["api_key"] = _env("CODEASSESS_LLM_KEY", "OPENAI_API_KEY",
                           default=conf.get("api_key", ""))
    conf["model"] = _env("CODEASSESS_LLM_MODEL", default=conf.get("model", ""))
    conf["enabled"] = bool(conf["base_url"] and conf["api_key"])
    return conf