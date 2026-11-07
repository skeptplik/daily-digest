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
    print("::error::Секреты TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы, сообщение НЕ отправлено.")
    sys.exit(1)

meta = json.loads(Path("out/meta.json").read_text(encoding="utf-8"))
data = json.loads(Path("data/digest.json").read_text(encoding="utf-8"))

ICONS = {"ai": "🤖", "health": "🩺", "science": "🔬", "space": "🚀", "politics": "🌍",
         "tech": "💻", "dev": "⌨️", "games": "🎮", "fashion": "👗", "security": "🔐", "curious": "🎈"}

items = [(t["id"], i) for t in data.get("topics", []) for i in t.get("items", [])]
total = len(items)
# 🔥 считает render.py по охвату (число изданий) и пишет в meta.json
hot = [(h["topic"], {"title": h["title"]}) for h in meta.get("hot", [])][:7]

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

from alert import send  # до 3 попыток при сетевой ошибке/429/5xx; токен не печатается

sys.exit(0 if send(text, preview=True) else 1)  # код 1 -> job notify красный -> publish.yml шлёт сигнал о сбое
