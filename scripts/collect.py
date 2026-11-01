#!/usr/bin/env python3
"""Собирает свежие заголовки из RSS-лент проверенных изданий (data/feeds.json)
и пишет data/candidates.json. Работает на GitHub Actions: там есть нормальный
доступ в интернет, а токены Claude не тратятся. Облачная задача Claude потом
выбирает из готового списка самое важное и пишет краткие пересказы."""
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
WINDOW_HOURS = 40
PER_TOPIC = {"politics": 30}
DEFAULT_PER_TOPIC = 14
UA = {"User-Agent": "Mozilla/5.0 (compatible; DailyDigestBot/1.0; +https://github.com)"}

feeds = json.loads((ROOT / "data/feeds.json").read_text(encoding="utf-8"))
src = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
trusted = {d for group in src["trusted"].values() for d in group} | set(src["primary"])


def is_trusted(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in trusted)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def clean(text: str, limit: int) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def parse_date(text: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_feed(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    for node in root.iter():
        if local(node.tag) not in ("item", "entry"):
            continue
        row = {"title": "", "link": "", "date": None, "summary": ""}
        for ch in node:
            name = local(ch.tag)
            if name == "title":
                row["title"] = clean(ch.text or "", 200)
            elif name == "link":
                row["link"] = (ch.get("href") or ch.text or "").strip() if not row["link"] or ch.get("rel") == "alternate" else row["link"]
            elif name in ("pubDate", "published", "updated", "date") and not row["date"]:
                row["date"] = parse_date(ch.text)
            elif name in ("description", "summary", "encoded", "content") and not row["summary"]:
                row["summary"] = clean(ch.text or "", 240)
        if row["title"] and row["link"]:
            yield row


def main() -> int:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=WINDOW_HOURS)
    topics, ok, failed = {}, 0, []
    for tid, lst in feeds.items():
        if tid.startswith("_"):
            continue
        per_outlet = []
        for f in lst:
            try:
                r = requests.get(f["url"], headers=UA, timeout=25)
                r.raise_for_status()
                rows = []
                for it in parse_feed(r.content):
                    if not it["date"] or it["date"] < since or it["date"] > now + timedelta(hours=2):
                        continue
                    if not is_trusted(it["link"]):
                        continue
                    rows.append({"outlet": f["outlet"], "title": it["title"], "link": it["link"],
                                 "published": it["date"].strftime("%Y-%m-%d %H:%M"), "summary": it["summary"]})
                rows.sort(key=lambda x: x["published"], reverse=True)
                per_outlet.append(rows)
                ok += 1
                print(f"ok   {tid:9} {f['outlet']}: {len(rows)}")
            except Exception as e:  # одна упавшая лента не должна ломать сборку
                failed.append(f"{tid}/{f['outlet']}: {type(e).__name__}")
                print(f"FAIL {tid:9} {f['outlet']}: {type(e).__name__}")
        # по кругу берём из разных изданий, чтобы одно не заняло весь список
        picked, seen, i = [], set(), 0
        cap = PER_TOPIC.get(tid, DEFAULT_PER_TOPIC)
        while len(picked) < cap and any(i < len(rows) for rows in per_outlet):
            for rows in per_outlet:
                if i < len(rows) and rows[i]["link"] not in seen and len(picked) < cap:
                    seen.add(rows[i]["link"])
                    picked.append(rows[i])
            i += 1
        topics[tid] = picked

    total = sum(len(v) for v in topics.values())
    out = {"generated_at": now.strftime("%Y-%m-%d %H:%M UTC"), "window_hours": WINDOW_HOURS,
           "feeds_ok": ok, "feeds_failed": failed, "topics": topics}
    (ROOT / "data/candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Итого заголовков: {total}, лент ок: {ok}, с ошибкой: {len(failed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
