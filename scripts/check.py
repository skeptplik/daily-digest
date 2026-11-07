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
site_unknown = None  # сайт не удалось проверить (сеть/таймаут)
try:
    digest = json.loads((ROOT / "data/digest.json").read_text(encoding="utf-8"))
    if digest.get("demo"):
        problems.append("на сайте пока демо-страница, настоящий дайджест ещё ни разу не публиковался")
    elif digest.get("date") != today:
        problems.append(f"последний дайджест датирован {digest.get('date')}, а нужен {today}")
except Exception as e:
    problems.append(f"не удалось прочитать data/digest.json ({type(e).__name__})")

# сайт на GitHub Pages тоже должен показывать сегодняшний дайджест (ловит сбой публикации/проверки)
if not problems:
    try:
        import re
        owner = os.environ.get("GITHUB_REPOSITORY", "skeptplik/daily-digest").split("/")
        page = requests.get(f"https://{owner[0].lower()}.github.io/{owner[1]}/?t={today}", timeout=30).text
        m = re.search(r'<meta name="digest-date" content="(\d{4}-\d{2}-\d{2})"', page)
        if not m:
            problems.append("на сайте не нашлась дата дайджеста (страница не открылась или пустая)")
        elif m.group(1) != today:
            problems.append(f"файл дайджеста обновлён, но сайт показывает {m.group(1)}: "
                            "откройте Actions → Publish digest, возможно сборка упала на проверке данных")
    except Exception as e:
        site_unknown = type(e).__name__
        print("warn: сайт не проверен:", site_unknown)

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

if not problems and not site_unknown:
    print("Дайджест на месте:", today)
    sys.exit(0)

if problems:
    text = "⚠️ Дайджест на сегодня не собран.\n\n" + "\n".join(f"• {p}" for p in problems)
else:  # файл свежий, но страницу проверить не удалось: молчать нельзя, но и объявлять сбой рано
    text = ("⚠️ Файл дайджеста за сегодня есть, но сайт проверить не удалось (" + site_unknown + "). "
            "Откройте страницу дайджеста и убедитесь, что там сегодняшняя дата; если нет, "
            "проверьте GitHub → Actions → Publish digest.")
try:
    engine = json.loads((ROOT / "data/engine.json").read_text(encoding="utf-8")).get("engine", "claude")
except Exception:
    engine = "claude"
if not problems:
    pass  # сайт не проверен: перезапускать задачу не нужно (будет дубль в Telegram)
elif engine == "codex":
    text += "\n\nАктивный движок: Codex. Что сделать: откройте автоматизацию дайджеста в Codex и запустите её вручную."
else:
    text += "\n\nАктивный движок: Claude. Что сделать: claude.ai/code/routines → «Утренний дайджест» → Run now."
print(text)


def alerted_earlier_today() -> bool:
    """Запасной запуск по расписанию молчит, если более ранний запуск Check сегодня уже упал (значит, сообщил).
    Нужен GITHUB_TOKEN с правом actions: read (check.yml). Ручной запуск (workflow_dispatch) всегда шлёт."""
    tok, repo = os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_REPOSITORY", "")
    if not tok or not repo or os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        return False
    try:
        utc_day = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d")
        r = requests.get(f"https://api.github.com/repos/{repo}/actions/workflows/check.yml/runs",
                         params={"created": f">={utc_day}", "event": "schedule", "per_page": 20},
                         headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
                         timeout=20)
        runs = r.json().get("workflow_runs", []) if r.ok else []
    except Exception:
        return False  # не узнали — лучше дубль, чем тишина
    me = os.environ.get("GITHUB_RUN_ID", "")
    return any(str(x.get("id")) != me and x.get("conclusion") == "failure" for x in runs)


if alerted_earlier_today():
    print("Более ранний запуск Check сегодня уже сообщил о проблеме: повторное сообщение не отправляю")
    sys.exit(1)
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
