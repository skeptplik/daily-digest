#!/usr/bin/env python3
"""Проверка файла темы от субагента: python3 scripts/check_part.py <id темы> [/tmp/parts] [/tmp/topics]

Печатает короткий список ошибок или «OK ...». Субагенту не нужно писать свои проверки и скрипты сборки:
достаточно записать JSON одной командой записи и запустить этот скрипт.
Проверяет: JSON, лимиты длины (title 110, summary 280, why 120), число абзацев (основные 5-12, мелкие 2-5, если есть body),
ссылки sources есть в /tmp/topics/<id>.json, importance 1-2, число мелких (ровно 4, если материала хватает; больше 4 ошибка) и основных (до 5).
"""
import json
import sys
from pathlib import Path

tid = sys.argv[1]
parts = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/parts")
topics = Path(sys.argv[3] if len(sys.argv) > 3 else "/tmp/topics")
err, warn = [], []
try:
    d = json.loads((parts / f"{tid}.json").read_text(encoding="utf-8"))
except Exception as e:
    print(f"ОШИБКА: {tid}.json не читается ({type(e).__name__}: {e})")
    sys.exit(1)
links, roundup = set(), set()
tf = topics / f"{tid}.json"
if tf.exists():
    t = json.loads(tf.read_text(encoding="utf-8"))
    rows = t.get("rows") if isinstance(t, dict) else t
    links = {r["link"] for r in rows or []}
    roundup = {r["link"] for r in rows or [] if r.get("roundup")}
else:
    warn.append("файла темы нет: ссылки sources не сверены с сырьём")
items = d.get("items") or []
minor = sum(1 for i in items if i.get("minor"))
main = len(items) - minor
for n, i in enumerate(items):
    name = f"#{n} {str(i.get('title', ''))[:40]}"
    for k, lim in (("title", 110), ("summary", 280), ("why", 120)):
        v = i.get(k) or ""
        if not v:
            err.append(f"{name}: нет {k}")
        elif len(v) > lim:
            err.append(f"{name}: {k} {len(v)} > {lim}")
    imp = i.get("importance")
    if isinstance(imp, bool) or imp not in (1, 2):
        err.append(f"{name}: importance должен быть 1 или 2")
    if not isinstance(i.get("minor", False), bool):
        err.append(f"{name}: minor должен быть true/false, а не {i.get('minor')!r}")
    mn = i.get("minutes")
    if isinstance(mn, bool) or not isinstance(mn, int) or not 1 <= mn <= 10:
        err.append(f"{name}: minutes должен быть целым 1-10")
    srcs = i.get("sources") or []
    if not 1 <= len(srcs) <= 3:
        err.append(f"{name}: источников {len(srcs)} (нужно 1-3)")
    for s in srcs:
        if not isinstance(s, dict) or not str(s.get("url", "")).startswith("http"):
            err.append(f"{name}: некорректный источник {s!r}"[:120])
        elif links and s.get("url") not in links:
            err.append(f"{name}: ссылка не из файла темы: {s.get('url')}")
        elif s.get("url") in roundup:
            warn.append(f"{name}: источник roundup (подборка/рассылка): если есть отдельная статья о событии, поставь её")
    body = i.get("body") or []
    if body and (not isinstance(body, list) or not all(isinstance(x, str) and x.strip() for x in body)):
        err.append(f"{name}: body должен быть списком непустых строк")
        body = []
    if body:
        lo, hi = (2, 5) if i.get("minor") else (5, 12)
        if not lo <= len(body) <= hi:
            warn.append(f"{name}: абзацев {len(body)} (ожидалось {lo}-{hi})")
if main > 5:
    err.append(f"основных {main} > 5")
if minor > 4:  # решение владельца: не больше 4 мелких на тему (routine_prompt.md, assemble.py, validate.py)
    err.append(f"мелких {minor} > 4: оставь 4 самых интересных, остальные убери")
if minor < 4:
    warn.append(f"мелких {minor} < 4: добери подходящие из файла темы или объясни в skipped")
for c in d.get("curious_candidates") or []:
    cn = f"curious «{str(c.get('title', ''))[:40]}»"
    if not c.get("title") or not c.get("sources"):
        err.append("curious_candidates: нет title или sources")
        continue
    for s in c.get("sources") or []:
        if not isinstance(s, dict) or not str(s.get("url", "")).startswith("http"):
            err.append(f"{cn}: некорректный источник")
        elif links and s.get("url") not in links:
            err.append(f"{cn}: ссылка не из файла темы: {s.get('url')}")
    cb = c.get("body") or []
    if cb and (not isinstance(cb, list) or not all(isinstance(x, str) and x.strip() for x in cb)):
        err.append(f"{cn}: body должен быть списком непустых строк")
for e in err:
    print("ОШИБКА:", e)
for w in warn:
    print("внимание:", w)
print(("OK" if not err else "ЕСТЬ ОШИБКИ") + f": основных {main}, мелких {minor}, curious {len(d.get('curious_candidates') or [])}")
sys.exit(1 if err else 0)
