#!/usr/bin/env python3
"""Проверяет data/digest.json (или файл из аргумента) перед публикацией.
Нужна, чтобы дайджест от ЛЮБОЙ модели (Claude, ChatGPT и др.) не сломал страницу
и не содержал ссылок, которых нет в собранных заголовках.
Код выхода 1, если есть ошибки. Предупреждения (warn) не блокируют."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOPIC_IDS = ["ai", "health", "science", "space", "politics", "tech", "dev", "games", "fashion", "security", "curious"]

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

known = set()
try:
    c = json.loads((ROOT / "data/candidates.json").read_text(encoding="utf-8"))
    if c.get("generated_at", "")[:10] == d.get("date"):
        known = {r["link"] for rows in c.get("topics", {}).values() for r in rows}
    else:  # заголовки уже обновились после этого дайджеста: сверять ссылки нечем
        warns.append("candidates.json собран в другой день, ссылки не сверены")
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
    if main_n > 5:
        warns.append(f"тема {tid}: {main_n} основных новостей (в промпте не больше 5)")
    if minor_n > 8:
        warns.append(f"тема {tid}: {minor_n} мелких плиток (в промпте не больше 8)")
    for n, it in enumerate(items, 1):
        where = f"{tid}#{n}"
        total += 1
        if not isinstance(it.get("title"), str) or not it["title"].strip():
            errors.append(f"{where}: нет title")
        elif len(it["title"]) > 160:
            warns.append(f"{where}: заголовок длиннее 160 символов (обрежется)")
        if not isinstance(it.get("summary"), str) or not it["summary"].strip():
            warns.append(f"{where}: пустой summary")
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
if hot > 7:
    warns.append(f"importance=3 у {hot} новостей (в промпте не больше 7)")
if total == 0:
    errors.append("нет ни одной новости")

for w in warns:
    print("warn:", w)
for e in errors:
    print("ОШИБКА:", e)
print(f"{path.name}: новостей {total}, важных {hot}, ошибок {len(errors)}, предупреждений {len(warns)}")
sys.exit(1 if errors else 0)
