# -*- coding: utf-8 -*-
"""大模型接口封装（OpenAI 兼容协议）。

无网络或未配置 API Key 时 available() 返回 False，出题与评分自动改用
本地规则引擎，保证系统在离线环境下也能完整演示。
"""
import json
import re
import urllib.error
import urllib.request

from .config import llm_config


def available():
    return llm_config().get("enabled", False)


def status():
    c = llm_config()
    return {
        "enabled": bool(c.get("enabled")),
        "model": c.get("model", ""),
        "base_url": c.get("base_url", ""),
    }


def chat(messages, temperature=0.2, timeout=None, json_mode=True):
    """调用 chat/completions，返回文本内容；失败返回 None。"""
    c = llm_config()
    if not c.get("enabled"):
        return None
    url = c["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": c.get("model") or "gpt-4o-mini",
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + c["api_key"],
        },
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout or c.get("timeout", 60)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None


def chat_json(messages, **kw):
    """要求模型输出 JSON 对象，容错解析（去掉```json 围栏）。"""
    text = chat(messages, **kw)
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except Exception:
        return None