# Архитектура

```
GitHub Actions (cron 21:47, 01:23, 03:07 UTC)  collect.yml
   scripts/collect.py: data/feeds.json (RSS) -> data/candidates.json  (коммит в main)
        |
облачная задача Claude 06:12 Варшава (Sonnet 5.5)  [claude.ai/code/routines]
   читает candidates.json + sources.json, пишет data/digest.json, git push origin main
        |
publish.yml (триггер: push с изменением data/digest.json, либо вручную)
   build:  scripts/render.py -> site/index.html + out/digest-DATE.html + out/meta.json
   deploy: GitHub Pages
   notify: scripts/notify.py -> одно сообщение в Telegram (с ссылкой)
        |
check.yml 06:13 и 07:41 UTC: проверка свежести; при сбое сообщение в Telegram
```

## Расписание
| Что | Когда (UTC) | Варшава зимой | Где настроено |
|---|---|---|---|
| collect | 21:47, 01:23, 03:07 (запасные запуски из-за опозданий cron) | 22:47, 02:23, 04:07 | `.github/workflows/collect.yml` |
| задача Claude | 05:12 (cron `CRON_TZ=Europe/Warsaw 12 6 * * *`) | 06:12 | claude.ai/code/routines |
| check | 06:13, 07:41 | 07:13, 08:41 | `.github/workflows/check.yml` |
Актуальность: Actions на GitHub могут задерживаться на минуты и даже часы (запуск 2 ноября пришёл с опозданием на 7 часов). Летом (UTC+2) всё кроме задачи Claude сдвинется на час позже по часам Варшавы; задача Claude остаётся 06:12 по Варшаве.

## Данные
`data/candidates.json`: `generated_at`, `window_hours`, `feeds_ok`, `feeds_failed[]`, `topics{id:[{outlet,title,link,published,summary,image}]}` (до 60 строк на тему, политика до 150, по кругу из разных изданий; поля строки: `id`, `has_text`, `group`; ключ `groups`).

`data/digest.json`:
```
{ "date": "СЕГОДНЯ", "news_date": "ВЧЕРА", "headline": "...",
  "topics": [ {"id": "ai|health|science|space|politics|tech|dev|games|fashion|security|curious",
     "items": [ {"title","summary","why","sources":[{"name","url"}],"importance":1..3,"minutes":1..10} ] } ] }
```
Поле `"demo": true` бывает только у демо-файла. Опциональные: `i18n`, `headline_i18n` (переводы отключены ради лимита).

## render.py: ключевые решения
- Метки достоверности по доменам из `sources.json`: ✅ несколько независимых изданий, 📄 первоисточник, ⚠️ одно издание (политика), ☝️ одно доверенное, ⚠️ вне списка. Псевдонимы: bbc.co.uk → bbc.com и т. п.
- Фото: явное поле `image`, затем для каждого источника: картинка из RSS (по ссылке из candidates), затем og:image. Скачивание с защитой от SSRF (`is_public`, ручные редиректы), ресайз 720x540 JPEG, встраивание data URI. До 40 фото.
- Сортировка: внутри темы по важности; темы по (max важность, сумма важности, привычный порядок); `curious` последняя.
- «Смотреть только важное» (`hot`): importance 3; если меньше 3 — добавляются 2; максимум 10.
- Страница самодостаточна (один HTML): истории, тап-зоны, удержание для паузы, прогресс-бары, кольца «просмотрено» в localStorage, светлая/тёмная тема, озвучка (`speechSynthesis`), переключатель RU/EN/DE показывается только если в данных есть переводы.

## Почему так (кратко)
Подробнее в `docs/DECISIONS.md`. Главное: облачная задача Claude не имеет надёжного доступа к сайтам без человека, поэтому весь интернет-доступ вынесен на GitHub Actions, а Claude только отбирает и пишет текст.
