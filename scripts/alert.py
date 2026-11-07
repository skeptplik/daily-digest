#!/usr/bin/env python3
"""Короткое сообщение о сбое в Telegram (секреты TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID из окружения).

  python scripts/alert.py "текст"                      отправить текст
  python scripts/alert.py --status data/run_status.json сообщение из статуса облачной задачи (run-status.yml)

send() повторяет отправку до 3 раз только при сетевой ошибке, 429 или 5xx: при ответе 200 повтора нет,
поэтому дубль возможен лишь в редком случае «Telegram принял, но ответ потерялся».
Токен и id чата не печатаются. Код выхода 0, если отправлено.
"""
import json
import os
import sys
import time

import requests

DELAYS = (0, 5, 20)  # секунды перед попытками


def send(text: str, preview: bool = False) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("::error::Секреты TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы, сообщение НЕ отправлено.")
        return False
    for n, delay in enumerate(DELAYS, 1):
        time.sleep(delay)
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              data={"chat_id": chat, "text": text[:4000],
                                    "disable_web_page_preview": "false" if preview else "true"}, timeout=30)
        except Exception as e:  # детали запроса не печатаем: в них токен
            print(f"попытка {n}: ошибка сети {type(e).__name__}")
            continue
        print(f"попытка {n}: sendMessage {r.status_code}")
        if r.ok:
            return True
        if r.status_code != 429 and r.status_code < 500:  # 400/401/403: повтор не поможет
            print("::error::Telegram отказал:", (r.json() if r.headers.get("content-type", "").startswith("application/json") else {}).get("description", ""))
            return False
    return False


def status_text(path: str) -> str | None:
    """Текст из data/run_status.json; None, если сообщать не о чем (status ok или файл битый)."""
    try:
        st = json.loads(open(path, encoding="utf-8").read())
    except Exception as e:
        return f"⚠️ Дайджест: задача записала статус, но он не читается ({type(e).__name__})."
    if st.get("status") == "ok":
        return None
    reason = str(st.get("reason") or "причина не указана")[:500]
    return (f"⚠️ Дайджест за {st.get('date', '?')} не опубликован: облачная задача сообщила о сбое.\n\n"
            f"Причина: {reason}\n\nЧто сделать: claude.ai/code/routines → «Утренний дайджест» → журнал запуска; "
            "после исправления Run now.")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--status":
        msg = status_text(sys.argv[2])
        if msg is None:
            print("Статус ok: сообщать не о чем")
            sys.exit(0)
    else:
        msg = " ".join(sys.argv[1:]).strip()
    if not msg:
        print("Нет текста")
        sys.exit(2)
    print(msg)
    sys.exit(0 if send(msg) else 1)
