#!/usr/bin/env python3
"""Показывает одну запись дайджеста вместе с текстами её статей: для сверки рассказа (шаг 5 routine_prompt.md).

  python3 scripts/show_item.py ai:3            запись №3 темы ai из /tmp/parts/ai.json (номер как в обзоре assemble.py)
  python3 scripts/show_item.py cur:2           curious_candidates №2 (номер как в обзоре assemble.py)
  python3 scripts/show_item.py --top 6         кандидаты на сверку: основные рассказы с наибольшим числом чисел и цитат
  --digest data/digest.json                    брать записи из собранного дайджеста (номер внутри темы в этом файле)
  --parts DIR (по умолчанию /tmp/parts), --articles DIR (data/articles), --chars N (знаков текста на статью, 5000)

Связь ссылки и текста: id = sha1(link)[:10] (как в collect.py), текст в data/articles/<id>.txt.
Печатает title, summary, sources, body и для каждого источника строку из candidates.json и текст статьи
(или пометку, что текста нет). Только стандартная библиотека, ничего не меняет.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOPICS = ["ai", "health", "science", "space", "politics", "tech", "dev", "games", "fashion", "security"]


def article_id(link: str) -> str:
    return hashlib.sha1(link.encode("utf-8")).hexdigest()[:10]


def load_topics(a):
    """{тема: [записи]} и общий список curious_candidates (в порядке обзора assemble.py)."""
    if a.digest:
        d = json.loads(Path(a.digest).read_text(encoding="utf-8"))
        return {t.get("id"): t.get("items") or [] for t in d.get("topics", [])}, []
    out, cur = {}, []
    for tid in TOPICS:
        f = Path(a.parts) / f"{tid}.json"
        if not f.exists():
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"!! {tid}: невалидный JSON ({type(e).__name__})")
            continue
        out[tid] = d.get("items") or []
        cur.extend(d.get("curious_candidates") or [])
    return out, cur


def score(it) -> int:
    """Сколько в рассказе проверяемых деталей: чисел и цитат."""
    text = " ".join(p for p in (it.get("body") or []) if isinstance(p, str))
    return len(re.findall(r"\d+(?:[.,]\d+)?", text)) + len(re.findall(r"[«\"“]", text))


def cand_rows():
    try:
        c = json.loads((ROOT / "data" / "candidates.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {r.get("link"): r for rows in (c.get("topics") or {}).values() for r in rows}


def show(it, where, a):
    rows = cand_rows()
    print(f"===== {where}: {it.get('title', '')}")
    print(f"summary: {it.get('summary', '')}")
    if it.get("why"):
        print(f"why: {it['why']}")
    print(f"importance {it.get('importance')} · minor {bool(it.get('minor'))}")
    body = it.get("body") or []
    print(f"--- body ({len(body)} абзацев)")
    for n, p in enumerate(body, 1):
        print(f"[{n}] {p}")
    for k, s in enumerate(it.get("sources") or [], 1):
        url = s.get("url", "") if isinstance(s, dict) else ""
        aid = article_id(url)
        r = rows.get(url) or {}
        print(f"\n--- источник {k}: {s.get('name', '') if isinstance(s, dict) else s} | {url}")
        if r:
            print(f"строка сырья: [{r.get('outlet')}] {r.get('title')} | {r.get('summary', '')}")
        else:
            print("строка сырья: ссылки нет в data/candidates.json")
        f = Path(a.articles) / f"{aid}.txt"
        if not f.exists():
            print(f"ТЕКСТА НЕТ (data/articles/{aid}.txt отсутствует): сверяй только с заголовком и описанием")
            continue
        text = f.read_text(encoding="utf-8")
        print(f"текст data/articles/{aid}.txt ({len(text)} знаков):")
        print(text[:a.chars])
        if len(text) > a.chars:
            print(f"… [обрезано на {a.chars} знаках; весь текст: --chars {len(text)}]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ref", nargs="*", help="тема:номер или cur:номер")
    ap.add_argument("--parts", default="/tmp/parts")
    ap.add_argument("--digest")
    ap.add_argument("--articles", default=str(ROOT / "data" / "articles"))
    ap.add_argument("--chars", type=int, default=5000)
    ap.add_argument("--top", type=int, default=0)
    a = ap.parse_args()
    topics, cur = load_topics(a)
    if a.top:
        ranked = sorted(((score(i), tid, n, i) for tid, items in topics.items() for n, i in enumerate(items)
                         if not i.get("minor") and i.get("body")), key=lambda x: -x[0])
        print("== кандидаты на сверку (чисел+цитат в рассказе, тема:номер, заголовок)")
        for sc, tid, n, i in ranked[:a.top]:
            print(f"  {sc:3} {tid}:{n} {str(i.get('title', ''))[:90]}")
    rc = 0
    for ref in a.ref:
        tid, _, num = ref.partition(":")
        try:
            n = int(num)
            it = cur[n] if tid == "cur" else topics[tid][n]
        except (ValueError, KeyError, IndexError):
            known = ", ".join(f"{t}:0-{len(v) - 1}" for t, v in topics.items() if v)
            print(f"!! нет записи «{ref}». Есть: {known}" + (f", cur:0-{len(cur) - 1}" if cur else ""))
            rc = 2
            continue
        show(it, ref, a)
    if not a.ref and not a.top:
        ap.print_help()
    return rc


if __name__ == "__main__":
    sys.exit(main())
