#!/usr/bin/env python3
"""Сборка data/digest.json из результатов субагентов (/tmp/parts/<тема>.json).

Зачем: облачная задача не должна читать рассказы (body) в свой контекст целиком — это ~150 тыс. токенов,
которые потом перечитываются на каждом шаге. Скрипт печатает компактный обзор (заголовки, источники, число
абзацев), а итоговый файл собирает сам.

Обзор:   python3 scripts/assemble.py [--parts /tmp/parts]
Сборка:  python3 scripts/assemble.py --date 2026-11-05 --news-date 2026-11-04 --headline "..." \
             [--drop ai:3,tech:5] [--curious 0,2,4] [--out data/digest.json]
  --drop     убрать новости (тема:номер из обзора), например дубли между темами;
  --curious  номера историй из curious_candidates (в обзоре), 3-5 штук; сборка без этого флага тему curious не создаёт.
Номера в обзоре с нуля, как в файлах субагентов.
"""
import argparse
import json
import sys
from pathlib import Path

TOPICS = ["ai", "health", "science", "space", "politics", "tech", "dev", "games", "fashion", "security"]
SERVICE = {"independent", "note", "skipped", "demo"}
MIN_MINOR = 4  # правило routine_prompt.md: в теме не меньше 4 мелких, если материала хватает


def load(parts: Path, tid: str):
    f = parts / f"{tid}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # битый JSON: задача делает эту тему сама
        print(f"!! {tid}: невалидный JSON ({type(e).__name__})")
        return None


def clean_item(it: dict) -> dict:
    out = {k: v for k, v in it.items() if k not in SERVICE}
    out.setdefault("importance", 1)
    try:
        out["importance"] = max(1, min(int(out["importance"]), 2))  # 3 ставит render.py
    except (TypeError, ValueError):
        out["importance"] = 1
    out.setdefault("minor", False)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", default="/tmp/parts")
    ap.add_argument("--drop", default="")
    ap.add_argument("--curious", default="")
    ap.add_argument("--date")
    ap.add_argument("--news-date")
    ap.add_argument("--headline")
    ap.add_argument("--out")
    a = ap.parse_args()
    parts = Path(a.parts)
    drop = {tuple(x.strip().split(":", 1)) for x in a.drop.split(",") if x.strip()}
    data, cur_all = {}, []
    for tid in TOPICS:
        d = load(parts, tid)
        if d is None:
            print(f"!! {tid}: файла нет или он невалиден — тему делает задача сама")
            continue
        data[tid] = d
        for c in d.get("curious_candidates") or []:
            cur_all.append(c)

    # неверный номер в --drop/--curious раньше молча ничего не делал (дубль оставался, история не бралась)
    bad = []
    for x in sorted(drop):
        tid, n = x if len(x) == 2 else (x[0], "")
        if tid not in data or not n.isdigit() or int(n) >= len(data[tid].get("items") or []):
            bad.append(f"--drop {':'.join(x)}")
    pick_raw = [x.strip() for x in a.curious.split(",") if x.strip()]
    for x in pick_raw:
        if not x.isdigit() or int(x) >= len(cur_all):
            bad.append(f"--curious {x} (есть 0-{len(cur_all) - 1})")
    if len(set(pick_raw)) != len(pick_raw):
        bad.append("--curious: номер повторяется")
    if bad:
        print("!! неверные номера: " + "; ".join(bad) + ". Номера из обзора: тема:номер с нуля. Исправь и повтори")
        return 2

    print("== ОБЗОР (номер с нуля; M = мелкая; п = абзацев рассказа)")
    for tid, d in data.items():
        items = d.get("items") or []
        minor = sum(1 for n, i in enumerate(items) if i.get("minor") and (tid, str(n)) not in drop)
        flag = "  <-- МЕНЬШЕ 4 МЕЛКИХ" if minor < MIN_MINOR else ""
        print(f"[{tid}] (с учётом --drop) мелких {minor}{flag}")
        for n, i in enumerate(items):
            srcs = len(i.get("sources") or [])
            mark = "M" if i.get("minor") else " "
            gone = " (убрана)" if (tid, str(n)) in drop else ""
            print(f"  {tid}:{n} {mark} {i.get('title', '')[:90]} | ист {srcs} | {len(i.get('body') or [])}п{gone}")
        if d.get("skipped"):
            print(f"  за бортом: {str(d['skipped'])[:300]}")
    print("== curious_candidates (номер с нуля)")
    for n, c in enumerate(cur_all):
        print(f"  {n} {c.get('title', '')[:90]} | {len(c.get('body') or [])}п")

    if not a.out:
        return 0
    if not (a.date and a.news_date and a.headline):
        print("!! для сборки нужны --date, --news-date, --headline")
        return 2
    missing = [t for t in TOPICS if t not in data]
    if missing:  # нет файла темы: не публиковать урезанный дайджест молча
        print("!! нет файлов/валидного JSON для тем: " + ", ".join(missing) +
              ". Сделай эти темы сам (или запиши {\"topic\": \"<id>\", \"items\": [], \"skipped\": \"почему пусто\"}, если материала правда нет) и повтори сборку")
        return 2
    topics, thin = [], []
    for tid in TOPICS:
        all_items = data[tid].get("items") or []
        items = [clean_item(i) for n, i in enumerate(all_items) if (tid, str(n)) not in drop]
        before = sum(1 for i in all_items if i.get("minor"))
        after = sum(1 for i in items if i.get("minor"))
        if after < MIN_MINOR and after < before:  # тему обеднил именно --drop
            thin.append(tid)
            print(f"внимание: после --drop в теме {tid} мелких {after} (было {before}, нужно от {MIN_MINOR}): "
                  "если в /tmp/topics/<тема>.json есть подходящие заголовки, добери мелкие и собери заново, иначе назови причину в отчёте")
        items.sort(key=lambda i: bool(i.get("minor")))  # основные первыми; порядок внутри сохраняется
        if not items:  # тема без материала (файл с пустым items): в итог не идёт
            print(f"внимание: тема {tid} пуста, пропущена ({str(data[tid].get('skipped') or 'без объяснения')[:120]})")
            continue
        topics.append({"id": tid, "items": items})
    pick = [int(x) for x in pick_raw]
    if pick:
        cur = []
        for n in pick:
            c = dict(cur_all[n])
            c.setdefault("why", "")
            c["importance"] = 1
            c["minor"] = False
            body = c.get("body") or []
            c["minutes"] = max(1, min(3, round(sum(len(p) for p in body) / 1200) or 1))
            if not body:
                c.pop("body", None)
            cur.append(c)
        topics.append({"id": "curious", "items": cur})
    out = {"date": a.date, "news_date": a.news_date, "headline": a.headline, "topics": topics}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(t["items"]) for t in topics)
    print(f"== записано {a.out}: тем {len(topics)}, новостей {total}")
    # метрики расхода: считает скрипт, а не модель (токены задаче не видны)
    body_chars = lambda i: sum(len(p) for p in (i.get("body") or []) if isinstance(p, str))
    dropped = [i for tid in TOPICS if tid in data for n, i in enumerate(data[tid].get("items") or []) if (tid, str(n)) in drop]
    metrics = {
        "items": total,
        "main": sum(1 for t in topics for i in t["items"] if not i.get("minor")),
        "minor": sum(1 for t in topics for i in t["items"] if i.get("minor")),
        "body_chars": sum(body_chars(i) for t in topics for i in t["items"]),
        "dropped_items": len(dropped),
        "dropped_body_chars": sum(body_chars(i) for i in dropped),
        "curious_written": len(cur_all),
        "curious_selected": len(pick),
        "curious_unused_body_chars": sum(body_chars(c) for n, c in enumerate(cur_all) if n not in pick),
        "missing_topics": [t for t in TOPICS if t not in data],
        "thin_after_drop": thin,
    }
    print("METRICS " + json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
