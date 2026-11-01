#!/usr/bin/env python3
"""Собирает HTML-дайджест из data/digest.json.

- подтягивает картинки (из поля image или og:image статей-источников) и вшивает их в файл,
  поэтому страница открывается офлайн;
- проверяет источники по data/sources.json и считает независимые подтверждения;
- данные в страницу передаются как JSON, весь текст экранируется на стороне страницы.
"""
import base64
import io
import ipaddress
import json
import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 40_000_000

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "digest.json"
SOURCES = ROOT / "data" / "sources.json"
SITE = ROOT / "site"
OUT = ROOT / "out"
NO_NET = os.environ.get("NO_NETWORK") == "1"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# id -> (название, эмодзи, цвет 1, цвет 2)
TOPICS = {
    "ai": ("Искусственный интеллект", "🤖", "#8b5cf6", "#6366f1"),
    "health": ("Медицина и здоровье", "🩺", "#10b981", "#14b8a6"),
    "science": ("Наука", "🔬", "#3b82f6", "#06b6d4"),
    "space": ("Космос", "🚀", "#6366f1", "#a855f7"),
    "politics": ("Политика и мир", "🌍", "#f59e0b", "#ef4444"),
    "tech": ("Технологии и железо", "💻", "#06b6d4", "#3b82f6"),
    "dev": ("Разработка и IT", "👨‍💻", "#22c55e", "#84cc16"),
    "games": ("Игры и индустрия", "🎮", "#ec4899", "#f43f5e"),
    "fashion": ("Мода и дизайн", "👗", "#f472b6", "#fb923c"),
    "security": ("Кибербезопасность", "🛡️", "#ef4444", "#f97316"),
    "curious": ("Любопытное", "🎈", "#eab308", "#f97316"),
}
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MAX_IMAGES = 40
# разные домены одного издания считаем одним источником
OUTLET_ALIASES = {"bbc.co.uk": "bbc.com", "voguebusiness.com": "vogue.com", "github.blog": "github.com"}


def human_date(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.day} {MONTHS[d.month - 1]}", WEEKDAYS[d.weekday()]


# ---------- источники ----------
def load_sources(demo):
    trusted, primary = set(), set()
    try:
        cfg = json.loads(SOURCES.read_text(encoding="utf-8"))
        for lst in cfg.get("trusted", {}).values():
            trusted.update(x.lower() for x in lst)
        primary.update(x.lower() for x in cfg.get("primary", []))
    except Exception as e:
        print("::warning::Не удалось прочитать data/sources.json:", type(e).__name__)
    if demo:  # в демо-данных используются выдуманные издания на example.com
        trusted.add("example.com")
    return trusted, primary


def match_domain(host, domains):
    host = (host or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for d in domains:
        if host == d or host.endswith("." + d):
            return d
    return None


# ---------- сеть и картинки ----------
def is_public(url):
    """Только http(s) и только публичные адреса (защита от обращения во внутренние сети)."""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        port = p.port or (443 if p.scheme == "https" else 80)
        for info in socket.getaddrinfo(p.hostname, port):
            if not ipaddress.ip_address(info[4][0]).is_global:
                return False
        return True
    except Exception:
        return False


def fetch(url, max_bytes, timeout=8, referer=None):
    """Скачивает url, вручную проходя редиректы и проверяя каждый адрес."""
    for _ in range(4):
        if not is_public(url):
            return None
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en,ru;q=0.8",
                                           "Accept": "text/html,image/avif,image/webp,image/*;q=0.8,*/*;q=0.5",
                                           **({"Referer": referer} if referer else {})},
                             timeout=timeout, stream=True, allow_redirects=False)
        except Exception:
            return None
        if r.status_code in (301, 302, 303, 307, 308):
            url = urljoin(url, r.headers.get("Location", ""))
            r.close()
            continue
        if r.status_code != 200:
            r.close()
            return None
        try:
            data = r.raw.read(max_bytes + 1, decode_content=True)
        except Exception:
            data = b""
        headers = r.headers
        r.close()
        if not data or len(data) > max_bytes:
            return None
        return headers, data, url
    return None


class OgParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image = None

    def handle_starttag(self, tag, attrs):
        if self.image:
            return
        a = dict(attrs)
        if tag == "link" and (a.get("rel") or "").lower() == "image_src" and a.get("href"):
            self.image = a["href"].strip()
            return
        if tag != "meta":
            return
        key = (a.get("property") or a.get("name") or "").lower()
        if key in ("og:image", "og:image:url", "twitter:image") and a.get("content"):
            self.image = a["content"].strip()


def og_image(page_url):
    res = fetch(page_url, 400_000)
    if not res:
        return None
    _, data, final_url = res
    p = OgParser()
    try:
        p.feed(data.decode("utf-8", errors="replace"))
    except Exception:
        return None
    return urljoin(final_url, p.image) if p.image else None


def to_data_uri(raw):
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        im = im.convert("RGB")
        if im.width < 240 or im.height < 120:
            return None
        im = ImageOps.fit(im, (720, 540), method=Image.LANCZOS)  # 4:3
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=72, optimize=True, progressive=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


RSS_IMAGES = {}  # ссылка на статью -> картинка из RSS (собирает scripts/collect.py)
STATS = {"rss": 0, "og": 0, "none": 0}


def load_rss_images():
    p = ROOT / "data" / "candidates.json"
    try:
        c = json.loads(p.read_text(encoding="utf-8"))
        for rows in c.get("topics", {}).values():
            for r in rows:
                if r.get("image"):
                    RSS_IMAGES[r["link"]] = r["image"]
    except Exception:
        pass


def try_image(url, referer):
    res = fetch(url, 3_000_000, timeout=10, referer=referer)
    return to_data_uri(res[1]) if res else None


def resolve_image(item):
    """Порядок: явная картинка, затем для каждого источника: картинка из RSS, затем og:image страницы."""
    if item.get("image"):
        uri = try_image(item["image"], None)
        if uri:
            return uri
    for src in item["sources"]:
        page = src["url"]
        origin = "{0.scheme}://{0.netloc}/".format(urlparse(page))
        if RSS_IMAGES.get(page):
            uri = try_image(RSS_IMAGES[page], origin)
            if uri:
                STATS["rss"] += 1
                return uri
        url = og_image(page)
        if url:
            uri = try_image(url, origin)
            if uri:
                STATS["og"] += 1
                return uri
    STATS["none"] += 1
    return None


def placeholder(item):
    """Нейтральная обложка для демо-превью (включается переменной PLACEHOLDER_IMAGES=1)."""
    import random
    from PIL import ImageDraw
    rnd = random.Random(item["title"])
    t = item["_topic"]
    ca = tuple(int(t["a"][i:i + 2], 16) for i in (1, 3, 5))
    cb = tuple(int(t["b"][i:i + 2], 16) for i in (1, 3, 5))
    mask = Image.linear_gradient("L").resize((720, 540)).rotate(rnd.choice([0, 90, 45]), expand=False)
    im = Image.composite(Image.new("RGB", (720, 540), cb), Image.new("RGB", (720, 540), ca), mask)
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for _ in range(4):
        x = rnd.randint(-200, 700)
        w = rnd.randint(40, 120)
        d.polygon([(x, 540), (x + w, 540), (x + w + 280, 0), (x + 280, 0)], fill=(255, 255, 255, rnd.randint(10, 26)))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------- нормализация данных ----------
def clean_url(u):
    if isinstance(u, str) and u.startswith(("http://", "https://")) and len(u) < 600:
        return u
    return None


def s(v, limit):
    return (v if isinstance(v, str) else "").strip()[:limit]


def norm_sources(it, trusted, primary):
    raw = []
    for x in (it.get("sources") or [])[:3]:
        if isinstance(x, dict) and clean_url(x.get("url")):
            raw.append((s(x.get("name"), 40), x["url"]))
    if not raw and clean_url(it.get("url")):
        raw.append((s(it.get("source"), 40), it["url"]))
    out, seen_outlets = [], set()
    for name, url in raw:
        host = urlparse(url).hostname or ""
        host_n = host[4:] if host.startswith("www.") else host
        t_dom = match_domain(host, trusted)
        p_dom = match_domain(host, primary)
        kind = "trusted" if t_dom else ("primary" if p_dom else "other")
        outlet = t_dom or p_dom or host_n
        if outlet == "example.com":  # демо: разные поддомены считаем разными изданиями
            outlet = host_n
        outlet = OUTLET_ALIASES.get(outlet, outlet)
        out.append({"name": name or host_n, "url": url, "kind": kind, "outlet": outlet})
    indep = len({x["outlet"] for x in out if x["kind"] == "trusted"})
    return out, indep


def main():
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    demo = bool(raw.get("demo"))
    trusted, primary = load_sources(demo)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_iso = raw.get("date") or today
    news_iso = raw.get("news_date") or date_iso
    day_h, weekday = human_date(date_iso)
    news_day_h, _ = human_date(news_iso)

    topics = []
    for t in raw.get("topics", []):
        tid = t.get("id")
        title, emoji, a, b = TOPICS.get(tid, (s(t.get("title"), 60) or "Другое", "📰", "#64748b", "#475569"))
        topic = {"id": tid or "x", "title": title, "emoji": emoji, "a": a, "b": b, "items": []}
        for it in t.get("items", [])[:5]:
            title_i = s(it.get("title"), 160)
            sources, indep = norm_sources(it, trusted, primary)
            if not title_i or not sources:
                continue
            try:
                imp = max(1, min(3, int(it.get("importance", 1))))
            except Exception:
                imp = 1
            try:
                minutes = max(1, min(15, int(it.get("minutes", 1))))
            except Exception:
                minutes = 1
            i18n = {}
            for lg in ("en", "de"):
                v = (it.get("i18n") or {}).get(lg)
                if isinstance(v, dict) and s(v.get("title"), 160):
                    i18n[lg] = {"title": s(v.get("title"), 160), "summary": s(v.get("summary"), 420),
                                "why": s(v.get("why"), 240)}
            topic["items"].append({
                "i18n": i18n,
                "title": title_i,
                "summary": s(it.get("summary"), 420),
                "why": s(it.get("why"), 240),
                "importance": imp,
                "minutes": minutes,
                "sources": sources,
                "indep": indep,
                "image": clean_url(it.get("image")),
                "img": None,
                "_topic": topic,
            })
        if topic["items"]:
            topics.append(topic)
    order = list(TOPICS)
    topics.sort(key=lambda t: order.index(t["id"]) if t["id"] in order else 99)
    all_items = [it for t in topics for it in t["items"]]

    if not NO_NET:
        load_rss_images()
        ranked = sorted(all_items, key=lambda i: -i["importance"])[:MAX_IMAGES]
        with ThreadPoolExecutor(8) as ex:
            for it, uri in zip(ranked, ex.map(resolve_image, ranked)):
                it["img"] = uri
        missing = sorted({urlparse(i["sources"][0]["url"]).hostname or "?" for i in ranked if not i["img"]})
        print(f"Фото: из RSS {STATS['rss']}, из og:image {STATS['og']}, не найдено {STATS['none']}")
        if missing:
            print("Без фото (источники, откуда не удалось взять обложку):", ", ".join(missing))

    if os.environ.get("PLACEHOLDER_IMAGES") == "1":
        for it in all_items:
            if not it["img"]:
                it["img"] = placeholder(it)
                it["ph"] = True

    for it in all_items:
        it.pop("_topic", None)
        it.pop("image", None)

    # статистика для журнала запуска
    single = [i["title"][:60] for t in topics if t["id"] == "politics" for i in t["items"] if i["indep"] < 2]
    if single:
        print("Политика: новости с одним независимым источником:", len(single))

    hi = raw.get("headline_i18n") if isinstance(raw.get("headline_i18n"), dict) else {}
    payload = {
        "date": date_iso, "news_iso": news_iso, "news_day": news_day_h, "headline": s(raw.get("headline"), 300),
        "headline_i18n": {lg: s(hi.get(lg), 300) for lg in ("en", "de") if s(hi.get(lg), 300)},
        "demo": demo, "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "topics": topics,
    }
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    html = env.get_template("digest.html").render(
        data=payload, date_iso=date_iso, date_human=day_h, weekday=weekday, news_day=news_day_h,
        headline=payload["headline"], demo=demo, total=len(all_items), ntopics=len(topics),
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    SITE.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    (SITE / "index.html").write_text(html, encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    (OUT / f"digest-{date_iso}.html").write_text(html, encoding="utf-8")
    (OUT / "meta.json").write_text(json.dumps({
        "date": date_iso, "news_day": news_day_h, "headline": payload["headline"],
        "demo": demo, "file": f"digest-{date_iso}.html",
        "important": sum(1 for i in all_items if i["importance"] == 3),
    }, ensure_ascii=False), encoding="utf-8")
    langs = [lg for lg in ("en", "de") if any(lg in i["i18n"] for i in all_items)]
    print("Языки перевода:", ", ".join(langs) if langs else "только русский")
    with_img = sum(1 for i in all_items if i["img"])
    print(f"OK: {len(all_items)} новостей, {len(topics)} тем, картинок: {with_img}, размер: {len(html) // 1024} КБ")


if __name__ == "__main__":
    sys.exit(main())
