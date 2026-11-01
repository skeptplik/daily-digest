#!/usr/bin/env python3
"""Отправляет в Telegram ссылку на дайджест и сам HTML-файл."""
import json
import os
import sys
from pathlib import Path

import requests

token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
page_url = os.environ.get("PAGE_URL", "").strip()

if not token or not chat:
    print("::warning::Секреты TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы, отправка пропущена.")
    sys.exit(0)

out = Path("out")
meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
api = f"https://api.telegram.org/bot{token}"

demo = "🧪 ДЕМО · " if meta.get("demo") else ""
text = f"{demo}☀️ Дайджест · события за {meta['news_day']}\n\n"
if meta.get("headline"):
    text += meta["headline"] + "\n\n"
text += f"🔗 {page_url}"

ok = True
try:
    r = requests.post(f"{api}/sendMessage", data={"chat_id": chat, "text": text}, timeout=30)
    print("sendMessage:", r.status_code, r.json().get("description", "ok"))
    ok &= r.ok

    path = out / meta["file"]
    with path.open("rb") as fh:
        r = requests.post(
            f"{api}/sendDocument",
            data={"chat_id": chat, "caption": "📎 Копия для чтения без интернета (с картинками)"},
            files={"document": (path.name, fh, "text/html")},
            timeout=120,
        )
    print("sendDocument:", r.status_code, r.json().get("description", "ok"))
    ok &= r.ok
except Exception as e:  # не печатаем детали запроса, чтобы не светить токен
    print("::error::Ошибка отправки в Telegram:", type(e).__name__)
    ok = False

sys.exit(0 if ok else 1)
