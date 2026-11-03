#!/usr/bin/env python3
"""Режет data/candidates.json на файлы по темам: <out>/<тема>.json.

Зачем: облачная задача отдаёт каждую тему отдельному субагенту, и раньше каждый
читал ВЕСЬ candidates.json (~100 тыс. токенов). Теперь он читает только свой файл:
строки темы + строки других тем, входящие в те же группы события (нужны для подсчёта
независимых изданий). Содержание строк не сокращается (title, summary, link, id,
has_text, group остаются как есть); убрано только поле image, которое задача не использует.

Запуск: python3 scripts/split_topics.py [папка_вывода]   (по умолчанию /tmp/topics)
Только стандартная библиотека. Данные в data/ не меняются.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "candidates.json"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/topics")
DROP = {"image"}


def slim(row, own_topic=None):
    r = {k: v for k, v in row.items() if k not in DROP}
    if own_topic:
        r["topic_of_row"] = own_topic  # строка из другой темы, взята из-за общей группы
    return r


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    topics = data.get("topics", {})
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()

    by_group = {}
    for tid, rows in topics.items():
        for r in rows:
            g = r.get("group")
            if g:
                by_group.setdefault(g, []).append((tid, r))

    total_rows = sum(len(v) for v in topics.values())
    with_text = sum(1 for v in topics.values() for r in v if r.get("has_text"))
    for tid, rows in topics.items():
        own_ids = {r.get("id") for r in rows}
        groups = {r["group"] for r in rows if r.get("group")}
        extra = []
        for g in sorted(groups):
            for t2, r2 in by_group.get(g, []):
                if t2 != tid and r2.get("id") not in own_ids:
                    extra.append(slim(r2, t2))
        meta = {
            "topic": tid,
            "generated_at": data.get("generated_at"),
            "rows_own": len(rows),
            "rows_from_other_topics": len(extra),
            "groups": [g for g in data.get("groups", []) if g.get("id") in groups],
        }
        lines = ['{"meta": ' + json.dumps(meta, ensure_ascii=False) + ',']
        lines.append(' "rows": [')
        all_rows = [slim(r) for r in rows] + extra
        for i, r in enumerate(all_rows):
            lines.append("  " + json.dumps(r, ensure_ascii=False) + ("," if i < len(all_rows) - 1 else ""))
        lines.append(" ]}")
        (OUT / f"{tid}.json").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"split_topics: generated_at={data.get('generated_at')} feeds_ok={data.get('feeds_ok')} "
          f"feeds_failed={len(data.get('feeds_failed') or [])} rows={total_rows} has_text={with_text}")
    for tid, rows in topics.items():
        size = (OUT / f"{tid}.json").stat().st_size // 1024
        print(f"  {tid}: {len(rows)} строк, файл {size} КБ")
    if total_rows and not with_text:
        print("ПРЕДУПРЕЖДЕНИЕ: у всех строк has_text=false, сырьё, вероятно, устарело")


if __name__ == "__main__":
    main()
