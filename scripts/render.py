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
import re
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
# DIGEST_FILE: отрисовать другой файл (например, дайджест от другой модели) только в out/preview-ИМЯ.html,
# не трогая site/ и рассылку (режим сравнения моделей)
PREVIEW_SRC = os.environ.get("DIGEST_FILE")
DATA = Path(PREVIEW_SRC).resolve() if PREVIEW_SRC else ROOT / "data" / "digest.json"
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
MAX_IMAGES = 160
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


def fetch(url, max_bytes, timeout=8, referer=None, prefix_ok=False):
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
        if prefix_ok:
            data = data[:max_bytes]   # для страницы нужно только начало (<head> с og:image)
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
    res = fetch(page_url, 400_000, prefix_ok=True)
    if not res:
        return None
    _, data, final_url = res
    p = OgParser()
    try:
        p.feed(data.decode("utf-8", errors="replace"))
    except Exception:
        return None
    return urljoin(final_url, p.image) if p.image else None


COVER_W, COVER_H = 800, 600   # обложка 4:3; малые картинки не растягиваем
GOOD_W = 700                  # такая ширина оригинала считается достаточно чёткой


def prep_image(raw):
    """Картинка -> (data URI WebP, ширина оригинала). Растягивать малые не будем: режем до 4:3 и ужимаем только вниз."""
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        im = im.convert("RGB")
        native_w = im.width
        if im.width < 240 or im.height < 120:
            return None, 0
        w, h = im.size
        # обрезка до 4:3 по центру (чуть выше центра: лица и заголовки обычно вверху)
        if w * 3 > h * 4:
            nw = h * 4 // 3
            x0 = (w - nw) // 2
            im = im.crop((x0, 0, x0 + nw, h))
        else:
            nh = w * 3 // 4
            y0 = max(0, int((h - nh) * 0.35))
            im = im.crop((0, y0, w, y0 + nh))
        if im.width > COVER_W:
            im = im.resize((COVER_W, COVER_H), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=74, method=6)
        return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode(), native_w
    except Exception:
        return None, 0


def externalize_images(payload):
    """Копия payload, где data-URI картинок заменены относительными ссылками img/<хеш>.<ext>; файлы пишутся в site/img."""
    import copy
    import hashlib
    import shutil
    img_dir = SITE / "img"
    shutil.rmtree(img_dir, ignore_errors=True)
    img_dir.mkdir(parents=True, exist_ok=True)
    pat = re.compile(r"^data:image/([a-z]+);base64,(.+)$", re.S)

    def save(uri):
        m = pat.match(uri) if isinstance(uri, str) else None
        if not m:
            return uri
        raw = base64.b64decode(m.group(2))
        name = hashlib.sha1(raw).hexdigest()[:16] + "." + ("jpg" if m.group(1) == "jpeg" else m.group(1))
        (img_dir / name).write_bytes(raw)
        return "img/" + name

    out = copy.deepcopy(payload)
    for t in out["topics"]:
        for it in t["items"]:
            it["img"] = save(it.get("img"))
            it["photos"] = [save(p) for p in it.get("photos") or []]
    return out


def to_data_uri(raw):
    return prep_image(raw)[0]


RSS_IMAGES = {}  # ссылка на статью -> картинка из RSS (собирает scripts/collect.py)
STATS = {"rss": 0, "og": 0, "none": 0}


def load_rss_images():
    p = ROOT / "data" / "candidates.json"
    try:
        c = json.loads(p.read_text(encoding="utf-8"))
        for rows in c.get("topics", {}).values():
            for r in rows:
                if r.get("image"):
                    # BBC отдаёт в RSS значок 240 px; та же картинка шириной 800 доступна по тому же пути
                    RSS_IMAGES[r["link"]] = re.sub(r"(ichef\.bbci\.co\.uk/ace/standard/)\d+/", r"\g<1>800/", r["image"])
    except Exception:
        pass


def try_image(url, referer):
    """(data URI, ширина оригинала) или (None, 0)."""
    res = fetch(url, 3_000_000, timeout=10, referer=referer)
    return prep_image(res[1]) if res else (None, 0)


def resolve_image(item):
    """Обложка: из всех кандидатов (явная, RSS и og:image каждого источника) берём самую чёткую.
    Если очередная картинка шире GOOD_W, сразу её, иначе пробуем следующую и берём лучшую."""
    best = (None, 0, None, None)  # uri, ширина, url, тип
    tried = 0

    def consider(url, origin, kind):
        nonlocal best, tried
        if not url or tried >= 5:
            return False
        tried += 1
        uri, w = try_image(url, origin)
        if uri and w > best[1]:
            best = (uri, w, url, kind)
        return best[1] >= GOOD_W

    if consider(item.get("image"), None, "rss"):
        pass
    else:
        for src in item["sources"]:
            page = src["url"]
            origin = "{0.scheme}://{0.netloc}/".format(urlparse(page))
            if consider(RSS_IMAGES.get(page), origin, "rss"):
                break
            if consider(og_image(page), origin, "og"):
                break
    if best[0]:
        STATS["rss" if best[3] == "rss" else "og"] += 1
        item["_cover_url"] = best[2]
        return best[0]
    STATS["none"] += 1
    return None


MAX_PHOTOS = 2


def resolve_photos(item):
    """Дополнительные фото для читалки: картинки других источников той же новости (RSS и og:image),
    кроме обложки. Берём не больше MAX_PHOTOS."""
    out, seen = [], {item.get("_cover_url")}
    for src in item["sources"]:
        page = src["url"]
        origin = "{0.scheme}://{0.netloc}/".format(urlparse(page))
        for url in (RSS_IMAGES.get(page), None if len(out) >= MAX_PHOTOS else og_image(page)):
            if not url or url in seen or len(out) >= MAX_PHOTOS:
                continue
            seen.add(url)
            uri, w = try_image(url, origin)
            if uri and w >= 400:
                out.append(uri)
    return out


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


HOT_MIN_OUTLETS = 3   # столько независимых изданий нужно событию для 🔥
HOT_SURE_OUTLETS = 4  # при таком охвате 🔥 ставится независимо от оценки ИИ
HOT_MAX = 5           # не больше стольких 🔥 за день
TOPIC_WEIGHT = {"politics": 1.5}   # мировые события при отборе 🔥 весят больше узких тем


# live-ленты в старом сырье без поля roundup (новое сырьё помечает их и рассылки в collect.py).
# Раньше было \blive\b: выкидывало обычные статьи вроде «Brand That Can Live Beyond Her».
LIVE_RE = re.compile(r"(?<!now )\blive(?: updates| blog| results)?:|(?<!watch it )\blive(?: updates| blog)?\s*$|"
                     r"\blive (?:blog|updates)\b|as it happened|/live/|/live-\d|/liveblog/|live-updates|/\d{8}-live-", re.I)


def load_reach(trusted, primary):
    """link -> group, group -> множество изданий из candidates.json (настоящий охват события)
    и множество ссылок-подборок (рассылки, бюллетени, live-ленты), которые охватом не считаются.
    Ссылка ведёт к группе, только если в группе есть ещё строка на том же языке: русско-английские
    склейки самые ненадёжные (7 ноября русская статья BBC об инвесторах ИИ попала в группу про Cybertruck,
    и «Акции ИИ упали» получили охват 5 вместо 3). Группа, где язык представлен хотя бы двумя строками, остаётся."""
    link_group, group_outlets, multi = {}, {}, set()
    langs = {}  # group -> [строк на английском и др., строк на русском]
    link_ru = {}
    try:
        cand = json.loads((ROOT / "data" / "candidates.json").read_text(encoding="utf-8"))
    except Exception:
        return link_group, group_outlets, multi
    for rows in (cand.get("topics") or {}).values():
        for r in rows:
            g, link = r.get("group"), r.get("link")
            if not link:
                continue
            # подборки и live-ленты охватывают много событий сразу: к группе их не привязываем
            if r.get("roundup") or LIVE_RE.search(f"{r.get('title','')} {link}"):
                multi.add(link)
                continue
            if g is None:
                continue
            host = urlparse(link).hostname or ""
            host_n = host[4:] if host.startswith("www.") else host
            outlet = match_domain(host, trusted) or match_domain(host, primary) or host_n
            outlet = OUTLET_ALIASES.get(outlet, outlet)
            link_group[link] = g
            group_outlets.setdefault(g, set()).add(outlet)
            ru = bool(re.search("[а-яё]", r.get("title", "").lower()))
            link_ru[link] = ru
            langs.setdefault(g, [0, 0])[ru] += 1
    for link, g in list(link_group.items()):
        if langs[g][link_ru[link]] < 2:  # единственная строка своего языка в группе: склейка через язык
            del link_group[link]
    return link_group, group_outlets, multi


def main():
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    demo = bool(raw.get("demo"))
    trusted, primary = load_sources(demo)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_iso = raw.get("date") or today
    news_iso = raw.get("news_date") or date_iso
    day_h, weekday = human_date(date_iso)
    news_day_h, _ = human_date(news_iso)

    link_group, group_outlets, multi = load_reach(trusted, primary)
    topics = []
    for t in raw.get("topics", []):
        tid = t.get("id")
        title, emoji, a, b = TOPICS.get(tid, (s(t.get("title"), 60) or "Другое", "📰", "#64748b", "#475569"))
        topic = {"id": tid or "x", "title": title, "emoji": emoji, "a": a, "b": b, "items": []}
        for it in t.get("items", [])[:14]:
            title_i = s(it.get("title"), 160)
            sources, indep = norm_sources(it, trusted, primary)
            if not title_i or not sources:
                continue
            # охват: все издания, писавшие об этом событии (по группе из candidates.json)
            # подборка или live-лента в sources подтверждением не считается (но одна такая ссылка = одно издание)
            reach = {x["outlet"] for x in sources if x["kind"] == "trusted" and x["url"] not in multi}
            # группы источников складываются: русская и английская группы одного события часто раздельны
            # (7 ноября угрозы минирования: g32 по-русски + g5 по-английски = 6 изданий). Ошибочные
            # межъязыковые склейки отсекает load_reach.
            for x in sources:
                reach |= group_outlets.get(link_group.get(x["url"]), set())
            indep = max(len(reach), min(indep, 1))
            try:
                imp = max(1, min(3, int(it.get("importance", 1))))
            except Exception:
                imp = 1
            llm_imp = imp
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
            body = [s(x, 1800) for x in (it.get("body") or [])[:30] if isinstance(x, str) and s(x, 1800)]                 if isinstance(it.get("body"), list) else []
            topic["items"].append({
                "minor": bool(it.get("minor")),
                "body": body,
                "i18n": i18n,
                "title": title_i,
                "summary": s(it.get("summary"), 420),
                "why": s(it.get("why"), 240),
                "importance": imp,
                "llm": llm_imp,
                "minutes": minutes,
                "sources": sources,
                "indep": indep,
                "image": clean_url(it.get("image")),
                "img": None,
                "photos": [],
                "_topic": topic,
            })
        if topic["items"]:
            topics.append(topic)
    order = list(TOPICS)
    # важность считает скрипт по охвату: 🔥 только событию, о котором писали
    # HOT_MIN_OUTLETS+ независимых изданий и которое ИИ не счёл мелочью (llm >= 2);
    # из них не больше HOT_MAX с самым большим охватом. ИИ может лишь снять 🔥.
    pool = [i for t in topics for i in t["items"] if not i["minor"]]
    tw = {id(i): TOPIC_WEIGHT.get(t["id"], 1) for t in topics for i in t["items"]}
    # при охвате HOT_SURE_OUTLETS+ изданий оценка ИИ не нужна: событие, о котором написали столько
    # независимых изданий, значимо само по себе (оценка ИИ шумит и иногда занижает самое крупное)
    cand_hot = sorted((i for i in pool if i["indep"] >= HOT_MIN_OUTLETS and (i["llm"] >= 2 or i["indep"] >= HOT_SURE_OUTLETS)),
                      key=lambda i: (-i["indep"] * tw[id(i)], -i["llm"]))
    hot_ids = {id(i) for i in cand_hot[:HOT_MAX]}
    for i in pool:
        if id(i) in hot_ids:
            i["importance"] = 3
        elif i["llm"] >= 2 or i["indep"] >= 2:
            i["importance"] = 2
        else:
            i["importance"] = 1
    for t in topics:
        for i in t["items"]:
            if i["minor"]:
                i["importance"] = min(i["importance"], 2) if i["indep"] >= 2 else 1
    # внутри темы: сначала основные, выше те, у кого важнее и больше охват
    for t in topics:
        t["items"].sort(key=lambda i: (i["minor"], -i["importance"], -i["indep"], -i["llm"]))

    # темы: чем важнее новости, тем выше тема; «Любопытное» всегда последняя;
    # при равенстве работает привычный порядок тем
    def topic_rank(t):
        imps = [i["importance"] for i in t["items"]]
        pos = order.index(t["id"]) if t["id"] in order else 99
        return (t["id"] == "curious", -max(imps), -sum(imps), pos)

    topics.sort(key=topic_rank)
    all_items = [it for t in topics for it in t["items"]]

    if not NO_NET:
        load_rss_images()
        ranked = sorted(all_items, key=lambda i: -i["importance"])[:MAX_IMAGES]
        with ThreadPoolExecutor(8) as ex:
            for it, uri in zip(ranked, ex.map(resolve_image, ranked)):
                it["img"] = uri
        with_body = [i for i in ranked if i["body"]]
        with ThreadPoolExecutor(8) as ex:
            for it, ph in zip(with_body, ex.map(resolve_photos, with_body)):
                it["photos"] = ph
        print(f"Читалка: статей с текстом {len(with_body)}, дополнительных фото {sum(len(i['photos']) for i in with_body)}")
        missing = sorted({urlparse(i["sources"][0]["url"]).hostname or "?" for i in ranked if not i["img"]})
        print(f"Фото: из RSS {STATS['rss']}, из og:image {STATS['og']}, не найдено {STATS['none']}")
        if missing:
            print("Без фото (источники, откуда не удалось взять обложку):", ", ".join(missing))

    if os.environ.get("PLACEHOLDER_IMAGES") == "1":
        for it in all_items:
            if not it["img"]:
                it["img"] = placeholder(it)
                it["ph"] = True

    # демо без сети: заглушки вместо дополнительных фото, чтобы видеть вёрстку читалки
    if os.environ.get("PLACEHOLDER_IMAGES") == "1":
        for it in all_items:
            if it["body"] and not it["photos"]:
                it["photos"] = [placeholder({**it, "title": it["title"] + str(k), "_topic": it["_topic"]}) for k in (1, 2)]

    for it in all_items:
        it.pop("_topic", None)
        it.pop("image", None)
        it.pop("_cover_url", None)

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
    if PREVIEW_SRC:
        target = OUT / f"preview-{DATA.stem}.html"
        target.write_text(html, encoding="utf-8")
        print(f"Предпросмотр: {target} ({len(all_items)} новостей, {len(topics)} тем)")
        return 0
    (OUT / f"digest-{date_iso}.html").write_text(html, encoding="utf-8")
    # сайт: картинки отдельными файлами site/img (страница ~1 МБ вместо ~8 МБ), архив в out/ остаётся самодостаточным
    site_payload = externalize_images(payload)
    html_site = env.get_template("digest.html").render(
        data=site_payload, date_iso=date_iso, date_human=day_h, weekday=weekday, news_day=news_day_h,
        headline=payload["headline"], demo=demo, total=len(all_items), ntopics=len(topics),
        generated=payload["generated"],
    )
    (SITE / "index.html").write_text(html_site, encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    (OUT / "meta.json").write_text(json.dumps({
        "date": date_iso, "news_day": news_day_h, "headline": payload["headline"],
        "demo": demo, "file": f"digest-{date_iso}.html",
        "important": sum(1 for i in all_items if i["importance"] == 3),
        "hot": [{"topic": t["id"], "title": i["title"], "n": i["indep"]}
                for t in topics for i in t["items"] if i["importance"] == 3],
    }, ensure_ascii=False), encoding="utf-8")
    langs = [lg for lg in ("en", "de") if any(lg in i["i18n"] for i in all_items)]
    print("Языки перевода:", ", ".join(langs) if langs else "только русский")
    with_img = sum(1 for i in all_items if i["img"])
    print(f"OK: {len(all_items)} новостей, {len(topics)} тем, картинок: {with_img}, размер страницы: {len(html_site) // 1024} КБ, архив: {len(html) // 1024} КБ")


if __name__ == "__main__":
    sys.exit(main())
