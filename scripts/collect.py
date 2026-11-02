#!/usr/bin/env python3
"""Собирает свежие заголовки из RSS-лент проверенных изданий (data/feeds.json)
и пишет data/candidates.json. Работает на GitHub Actions: там есть нормальный
доступ в интернет, а токены Claude не тратятся. Облачная задача Claude потом
выбирает из готового списка самое важное и пишет краткие пересказы."""
import hashlib
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
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parent.parent
WINDOW_HOURS = 40
PER_TOPIC = {"politics": 30}
DEFAULT_PER_TOPIC = 14
UA = {"User-Agent": "Mozilla/5.0 (compatible; DailyDigestBot/1.0; +https://github.com)"}

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
              "Accept-Language": "en,ru;q=0.8"}
# платные издания: полный текст не сохраняем (страницы дайджеста публичные), только заголовок и описание из RSS
PAYWALLED = {"nytimes.com", "wsj.com", "ft.com", "economist.com", "bloomberg.com", "washingtonpost.com"}
ARTICLE_CHARS = 20000
ARTICLES_DIR = ROOT / "data" / "articles"

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


MEDIA_NS = "{http://search.yahoo.com/mrss/}"
IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)", re.I)


def abs_img(u):
    u = html.unescape((u or "").strip())
    return u if u.startswith("http://") or u.startswith("https://") else ""


def parse_feed(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    for node in root.iter():
        if local(node.tag) not in ("item", "entry"):
            continue
        row = {"title": "", "link": "", "date": None, "summary": "", "image": ""}
        media, thumb, enclosure, inline = "", "", "", ""
        for ch in node:
            name = local(ch.tag)
            if name == "title":
                row["title"] = clean(ch.text or "", 200)
            elif name == "link":
                row["link"] = (ch.get("href") or ch.text or "").strip() if not row["link"] or ch.get("rel") == "alternate" else row["link"]
            elif name in ("pubDate", "published", "updated", "date") and not row["date"]:
                row["date"] = parse_date(ch.text)
            elif name in ("description", "summary", "encoded", "content") and not ch.tag.startswith(MEDIA_NS):
                if not row["summary"]:
                    row["summary"] = clean(ch.text or "", 240)
                if not inline:
                    m = IMG_RE.search(html.unescape(ch.text or ""))
                    inline = abs_img(m.group(1)) if m else ""
            elif ch.tag.startswith(MEDIA_NS) and name == "content" and not media:
                if (ch.get("medium") == "image") or (ch.get("type") or "").startswith("image") or re.search(r"\.(jpe?g|png|webp)(\?|$)", ch.get("url") or "", re.I):
                    media = abs_img(ch.get("url"))
            elif ch.tag.startswith(MEDIA_NS) and name == "thumbnail" and not thumb:
                thumb = abs_img(ch.get("url"))
            elif name == "enclosure" and not enclosure and (ch.get("type") or "").startswith("image"):
                enclosure = abs_img(ch.get("url"))
        row["image"] = media or enclosure or inline or thumb
        if row["title"] and row["link"]:
            yield row


STOP = set("""this that with from have been were will would their there about after before over into more than they them
what when which while also said says says news how why who new year years today week their could should being only
для или как что это его все при она они еще уже после перед через между вчера сегодня году года время также которые
которая который этого этом чтобы если были было быть будет своих""".split())


def tokens(row):
    text = (row["title"] + " " + row["summary"][:140]).lower()
    return {w[:6] for w in re.findall(r"[a-zа-яё0-9]{4,}", text) if w not in STOP}


CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
              ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t",
               "u", "f", "h", "ts", "ch", "sh", "sh", "", "i", "", "e", "iu", "ia"]))


def skeleton(w):
    """Фонетический скелет слова: русское и английское написание одного имени дают один ключ
    (Binance/Бинанс, Trump/Трамп, Bulgaria/Болгарии). Грубо, но для подсказки о группе хватает."""
    w = w.lower()
    if re.search("[а-яё]", w):
        w = "".join(CYR.get(ch, ch) for ch in w)
    w = re.sub(r"c(?=[eiy])", "s", w)
    for a, b in (("ph", "f"), ("th", "t"), ("ck", "k"), ("kh", "h"), ("sch", "sh"), ("tch", "ch"), ("x", "ks"), ("w", "v")):
        w = w.replace(a, b)
    w = re.sub(r"[cq]", "k", w)
    w = re.sub(r"[jy]", "i", w)
    w = w.translate(str.maketrans("zgdb", "sktp"))
    w = re.sub(r"(.)+", r"", w)
    out = w[:1] + re.sub(r"[aeiou]", "", w[1:])
    return re.sub(r"(.)+", r"", out)[:5]


def is_ru(row):
    return bool(re.search("[а-яё]", row["title"].lower()))


def tokens_x(row):
    """Ключи для сравнения заголовков на разных языках: скелеты слов и числа."""
    text = (row["title"] + " " + row["summary"][:140]).lower()
    keys = {skeleton(w) for w in re.findall(r"[a-zа-яё]{4,}", text) if w not in STOP}
    keys = {k for k in keys if len(k) >= 3}
    return keys | {"#" + n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", text) if len(n) >= 2}


def group_rows(rows, min_score=0.25):
    """Группирует заголовки об одном событии (разные издания, один язык) по редким общим словам.
    Возвращает список групп: [{"id", "outlets", "ids"}] только из 2+ изданий."""
    from math import log
    toks = [tokens(r) for r in rows]
    toks_x = [tokens_x(r) for r in rows]
    df, df_x = {}, {}
    for t in toks:
        for w in t:
            df[w] = df.get(w, 0) + 1
    for t in toks_x:
        for w in t:
            df_x[w] = df_x.get(w, 0) + 1
    n = len(rows)
    idf = {w: log(n / c) for w, c in df.items()}
    idf_x = {w: log(n / c) for w, c in df_x.items()}
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if rows[i]["outlet"] == rows[j]["outlet"]:
                continue
            cross = is_ru(rows[i]) != is_ru(rows[j])  # русский и английский заголовок: сравниваем скелеты
            ti, tj, d = (toks_x[i], toks_x[j], idf_x) if cross else (toks[i], toks[j], idf)
            common = ti & tj
            if len(common) < (3 if cross else 2):
                continue
            w_common = sum(d[w] for w in common)
            w_min = min(sum(d[w] for w in ti), sum(d[w] for w in tj)) or 1
            # у пар на разных языках общих слов мало, поэтому доля ниже, а общих ключей нужно больше
            if w_common / w_min >= (0.15 if cross else min_score) and w_common >= (6 if cross else 3.5):
                parent[find(i)] = find(j)
    buckets = {}
    for i in range(n):
        buckets.setdefault(find(i), []).append(i)
    groups = []
    for members in buckets.values():
        outlets = sorted({rows[i]["outlet"] for i in members})
        if len(outlets) >= 2:
            groups.append({"outlets": outlets, "ids": [rows[i]["id"] for i in members]})
    for k, g in enumerate(sorted(groups, key=lambda g: -len(g["outlets"])), 1):
        g["id"] = f"g{k}"
    return groups


# служебные строки страниц, которые trafilatura иногда оставляет в тексте
JUNK_RE = re.compile(
    r"^(-\s*)?published(\s*[-:].*)?$|^updated\s*[-:].*$|^you must confirm your public display name|^please logout and then login|"
    r"^sign up (for|to) our|^subscribe (to|for|now)|^for stories about life in our changing world|^read more:?|"
    r"^related( articles| stories| topics)?:?$|^advertisement$|^share this (article|story)|^follow us on|^click here to|"
    r"^читайте также|^подписывайтесь|^follow .{0,40} on (x|facebook|instagram|twitter)|"
    r"^accuracy and availability of transcripts|^follow the twists and turns",
    re.I)


def strip_junk(text: str) -> str:
    lines = [l for l in text.splitlines() if l.strip() and not JUNK_RE.match(l.strip())]
    return chr(10).join(lines)


def article_id(link: str) -> str:
    return hashlib.sha1(link.encode("utf-8")).hexdigest()[:10]


def fetch_text(row):
    """Скачивает статью и вытаскивает основной текст. Возвращает True, если текст сохранён."""
    host = (urlparse(row["link"]).hostname or "").lower()
    if any(host == d or host.endswith("." + d) for d in PAYWALLED):
        return False
    try:
        import trafilatura
        r = requests.get(row["link"], headers=BROWSER_UA, timeout=25)
        if r.status_code != 200:
            return False
        text = trafilatura.extract(r.text, include_comments=False, include_tables=False, favor_precision=True) or ""
    except Exception:
        return False
    text = strip_junk(text)
    if len(text) < 400:  # слишком коротко: скорее всего заглушка или пейволл
        return False
    if len(text) > ARTICLE_CHARS:
        text = text[:ARTICLE_CHARS].rsplit(chr(10), 1)[0]
    (ARTICLES_DIR / f"{row['id']}.txt").write_text(text, encoding="utf-8")
    return True


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
                try:
                    r = requests.get(f["url"], headers=UA, timeout=25)
                    r.raise_for_status()
                except Exception:  # часть лент (CBC, Business of Fashion) отвечает только браузеру
                    r = requests.get(f["url"], headers=BROWSER_UA, timeout=25)
                    r.raise_for_status()
                rows = []
                for it in parse_feed(r.content):
                    if not it["date"] or it["date"] < since or it["date"] > now + timedelta(hours=2):
                        continue
                    if not is_trusted(it["link"]):
                        continue
                    rows.append({"outlet": f["outlet"], "title": it["title"], "link": it["link"],
                                 "published": it["date"].strftime("%Y-%m-%d %H:%M"), "summary": it["summary"],
                                 "image": it["image"]})
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

    rows_all = [r for v in topics.values() for r in v]
    for r in rows_all:
        r["id"] = article_id(r["link"])
    ARTICLES_DIR.mkdir(exist_ok=True)
    for old in ARTICLES_DIR.glob("*.txt"):  # вчерашние тексты не копим
        old.unlink()
    with ThreadPoolExecutor(8) as ex:
        got = list(ex.map(fetch_text, rows_all))
    for r, ok_ in zip(rows_all, got):
        r["has_text"] = bool(ok_)
    print(f"Тексты статей: сохранено {sum(got)} из {len(rows_all)}")
    groups = group_rows(rows_all)
    by_id = {r["id"]: r for r in rows_all}
    for g in sorted(groups, key=lambda g: g["id"]):
        for i in g["ids"]:
            by_id[i]["group"] = g["id"]
    print(f"События с 2+ изданиями: {len(groups)}")

    total = sum(len(v) for v in topics.values())
    out = {"generated_at": now.strftime("%Y-%m-%d %H:%M UTC"), "window_hours": WINDOW_HOURS,
           "feeds_ok": ok, "feeds_failed": failed, "groups": groups, "topics": topics}
    (ROOT / "data/candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Итого заголовков: {total}, лент ок: {ok}, с ошибкой: {len(failed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
