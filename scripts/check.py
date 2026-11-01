#!/usr/bin/env python3
"""Проверка утром: обновился ли дайджест. Если нет, шлёт в Telegram сообщение с причиной."""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
today = datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d")

problems = []
try:
    digest = json.loads((ROOT / "data/digest.json").read_text(encoding="utf-8"))
    if digest.get("demo"):
        problems.append("на сайте пока демо-страница, настоящий дайджест ещё ни разу не публиковался")
    elif digest.get("date") != today:
        problems.append(f"последний дайджест датирован {digest.get('date')}, а нужен {today}")
except Exception as e:
    problems.append(f"не удалось прочитать data/digest.json ({type(e).__name__})")

cand = None
try:
    cand = json.loads((ROOT / "data/candidates.json").read_text(encoding="utf-8"))
    if not cand.get("generated_at", "").startswith(today) and problems:
        problems.append(f"заголовки тоже не обновились (последний сбор: {cand.get('generated_at')}): "
                        "проверьте вкладку Actions, запуск Collect news")
    elif problems and cand.get("feeds_ok", 0) < 10:
        problems.append(f"сборщик заголовков загрузил только {cand.get('feeds_ok')} лент")
    elif problems:
        problems.append("заголовки собраны, значит не отработала задача Claude: откройте claude.ai/code/routines "
                        "и посмотрите последний запуск «Утренний дайджест»")
except Exception:
    if problems:
        problems.append("файл заголовков data/candidates.json не прочитался")

if not problems:
    print("Дайджест на месте:", today)
    sys.exit(0)

text = "⚠️ Дайджест на сегодня не собран.\n\n" + "\n".join(f"• {p}" for p in problems)
text += "\n\nЧто сделать: claude.ai/code/routines → «Утренний дайджест» → Run now."
print(text)
token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
if not token or not chat:
    print("::warning::Нет секретов Telegram, уведомление не отправлено")
    sys.exit(1)
try:
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text}, timeout=30)
    print("sendMessage:", r.status_code)
except Exception as e:
    print("::error::Ошибка отправки:", type(e).__name__)
sys.exit(1)  # красный запуск в Actions тоже заметен
