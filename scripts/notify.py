#!/usr/bin/env python3
"""Отправляет в Telegram ОДНО текстовое сообщение: главное за день и ссылка на дайджест."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
page_url = os.environ.get("PAGE_URL", "").strip()

if not token or not chat:
    print("::warning::Секреты TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы, отправка пропущена.")
    sys.exit(0)

meta = json.loads(Path("out/meta.json").read_text(encoding="utf-8"))
data = json.loads(Path("data/digest.json").read_text(encoding="utf-8"))

ICONS = {"ai": "🤖", "health": "🩺", "science": "🔬", "space": "🚀", "politics": "🌍",
         "tech": "💻", "dev": "⌨️", "games": "🎮", "fashion": "👗", "security": "🔐", "curious": "🎈"}

items = [(t["id"], i) for t in data.get("topics", []) for i in t.get("items", [])]
total = len(items)
hot = [(tid, i) for tid, i in items if i.get("importance") == 3][:7]
if not hot:  # на случай, если важных нет: берём самые заметные
    hot = [(tid, i) for tid, i in items if i.get("importance") == 2][:5]

demo = "🧪 ДЕМО · " if meta.get("demo") else ""
text = f"{demo}☀️ Дайджест · события за {meta['news_day']}\n"
if hot:
    text += "\n🔥 Главное:\n"
    for tid, i in hot:
        text += f"{ICONS.get(tid, '•')} {i['title']}\n"
# параметр в конце ссылки не даёт Telegram/браузеру показать вчерашнюю копию страницы из кэша
link = f"{page_url.rstrip('/')}/?d={meta['date']}-{datetime.now(timezone.utc).strftime('%H%M')}"
text += f"\nВсего новостей: {total}. Все темы, фото и источники внутри:\n🔗 {link}"
text = text[:4000]

try:
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text, "disable_web_page_preview": "false"},
                      timeout=30)
    print("sendMessage:", r.status_code, r.json().get("description", "ok"))
    sys.exit(0 if r.ok else 1)
except Exception as e:  # не печатаем детали запроса, чтобы не светить токен
    print("::error::Ошибка отправки в Telegram:", type(e).__name__)
    sys.exit(1)
