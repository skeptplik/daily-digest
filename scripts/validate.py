#!/usr/bin/env python3
"""Проверяет data/digest.json (или файл из аргумента) перед публикацией.
Нужна, чтобы дайджест от ЛЮБОЙ модели (Claude, ChatGPT и др.) не сломал страницу
и не содержал ссылок, которых нет в собранных заголовках.
Код выхода 1, если есть ошибки. Предупреждения (warn) не блокируют."""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOPIC_IDS = ["ai", "health", "science", "space", "politics", "tech", "dev", "games", "fashion", "security", "curious"]
# те же лимиты, что в routine_prompt.md и check_part.py (там это ошибка для субагента, здесь предупреждение:
# проверка перед публикацией не должна ронять рассылку из-за длины текста)
LIMITS = {"title": 110, "summary": 280, "why": 120}

path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/digest.json"
errors, warns = [], []

try:
    d = json.loads(path.read_text(encoding="utf-8"))
except Exception as e:
    print(f"ОШИБКА: {path.name} не читается как JSON ({type(e).__name__}: {e})")
    sys.exit(1)

if not d.get("demo"):
    for k in ("date", "news_date", "headline"):
        if not isinstance(d.get(k), str) or not d.get(k).strip():
            errors.append(f"нет поля {k}")
    for k in ("date", "news_date"):
        if isinstance(d.get(k), str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d[k]):
            errors.append(f"{k} должна быть вида ГГГГ-ММ-ДД, а не «{d[k]}»")
if not isinstance(d.get("topics"), list) or not d["topics"]:
    errors.append("topics пуст или не список")
    d["topics"] = []

def parse_utc(s):
    """«2026-11-07 01:17 UTC» или ISO-время -> datetime (UTC) или None."""
    s = (s or "").strip()
    for f in ("%Y-%m-%d %H:%M UTC", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, f).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        t = datetime.fromisoformat(s)
        return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except ValueError:
        return None


# Ссылки сверяются с тем candidates.json, по которому собран дайджест.
# 1) assemble.py пишет в дайджест candidates_generated_at: совпало со свежим сырьём — сверяем; не совпало
#    (Collect успел запушить новое сырьё между клоном и пушем задачи) — только предупреждение: ссылки уже
#    сверили check_part.py и validate.py в самой задаче, а ошибка здесь стоила бы всей рассылки.
# 2) поля нет (старые дайджесты, другие ИИ): сверяем, если сырью не больше 30 часов (то же правило, что
#    в промпте). Раньше сравнивалась календарная дата, и сбор 21:47 UTC прошлого дня выключал сверку молча.
#    VALIDATE_NOW=<ISO-время> подменяет «сейчас» (только для проверки на старых данных).
MAX_AGE = timedelta(hours=30)
known, roundup = set(), set()
try:
    c = json.loads((ROOT / "data/candidates.json").read_text(encoding="utf-8"))
    roundup = {r["link"] for rows in c.get("topics", {}).values() for r in rows if r.get("roundup")}
    cand_at = c.get("generated_at", "")
    made_from = d.get("candidates_generated_at")
    now = parse_utc(os.environ.get("VALIDATE_NOW", "")) or datetime.now(timezone.utc)
    gen = parse_utc(cand_at)
    if made_from:
        ok = made_from == cand_at
        why = f"дайджест собран по сырью {made_from}, а в репозитории сырьё {cand_at}: ссылки не сверены (их сверила задача)"
    else:
        ok = gen is not None and timedelta(hours=-1) <= now - gen <= MAX_AGE
        why = f"candidates.json собран {cand_at or '?'}, это старше 30 часов: ссылки не сверены"
    if ok:
        known = {r["link"] for rows in c.get("topics", {}).values() for r in rows}
    else:
        warns.append(why)
except Exception:
    warns.append("candidates.json не прочитан: ссылки не сверены")

total, hot, seen_ids = 0, 0, set()
for t in d["topics"]:
    tid = t.get("id")
    if tid not in TOPIC_IDS:
        errors.append(f"неизвестная тема «{tid}» (допустимо: {', '.join(TOPIC_IDS)})")
    if tid in seen_ids:
        errors.append(f"тема {tid} повторяется")
    seen_ids.add(tid)
    items = t.get("items")
    if not isinstance(items, list) or not items:
        errors.append(f"тема {tid}: нет items")
        continue
    main_n = sum(1 for x in items if not x.get("minor"))
    minor_n = len(items) - main_n
    if main_n > 5:  # в check_part.py это ошибка (субагент исправит), здесь только предупреждение
        warns.append(f"тема {tid}: {main_n} основных новостей (в промпте не больше 5)")
    if minor_n > 8:
        warns.append(f"тема {tid}: {minor_n} мелких плиток (в промпте не больше 8)")
    for n, it in enumerate(items, 1):
        where = f"{tid}#{n}"
        total += 1
        if not isinstance(it.get("title"), str) or not it["title"].strip():
            errors.append(f"{where}: нет title")
        if not isinstance(it.get("summary"), str) or not it["summary"].strip():
            warns.append(f"{where}: пустой summary")
        for k, lim in LIMITS.items():  # лимиты промпта; render.py обрезает только с запасом (160/420/240)
            if isinstance(it.get(k), str) and len(it[k]) > lim:
                warns.append(f"{where}: {k} {len(it[k])} знаков, в промпте до {lim}")
        if it.get("importance") not in (1, 2, 3):
            errors.append(f"{where}: importance должна быть 1, 2 или 3, а не «{it.get('importance')}»")
        elif it["importance"] == 3:
            hot += 1
        if "body" in it:
            b = it["body"]
            if not isinstance(b, list) or not all(isinstance(x, str) for x in b):
                errors.append(f"{where}: body должен быть списком строк")
            elif sum(len(x.split()) for x in b) > 1500:
                warns.append(f"{where}: body длиннее 1500 слов")
        srcs = it.get("sources")
        if not isinstance(srcs, list) or not srcs:
            errors.append(f"{where}: нет sources")
            continue
        for s in srcs:
            u = s.get("url") if isinstance(s, dict) else None
            if not isinstance(u, str) or not u.startswith("http"):
                errors.append(f"{where}: некорректная ссылка в sources")
            elif known and u not in known and not d.get("demo"):
                errors.append(f"{where}: ссылки нет в candidates.json (возможно, выдумана): {u[:90]}")
            elif u in roundup:
                warns.append(f"{where}: источник — подборка/рассылка/live-лента (roundup), лучше отдельная статья: {u[:90]}")
if hot:  # 🔥 (importance 3) считает render.py по охвату, ИИ ставит только 1-2; render всё равно пересчитает
    warns.append(f"importance=3 у {hot} новостей: 🔥 ставит render.py, в дайджесте должно быть 1 или 2")
if total == 0:
    errors.append("нет ни одной новости")

for w in warns:
    print("warn:", w)
for e in errors:
    print("ОШИБКА:", e)
print(f"{path.name}: новостей {total}, важных {hot}, ошибок {len(errors)}, предупреждений {len(warns)}")
sys.exit(1 if errors else 0)
