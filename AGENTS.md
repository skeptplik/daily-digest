# AGENTS.md — daily-digest

Инструкция для ИИ-агентов (Codex, Claude Code и других), работающих в этой папке. Люди: начните с `docs/SETUP-VSCODE.md`.

## Что это
Личный ежедневный новостной дайджест на русском для одного читателя (владелец GitHub `skeptplik`, репозиторий `skeptplik/daily-digest`, ветка `main`). Каждое утро (Польша, Europe/Warsaw) приходит одно сообщение в Telegram со ссылкой на красивую мобильную страницу в стиле историй.
Платных API нет и не планируется: LLM-шаг выполняет облачная задача Claude по подписке Pro.

## Карта проекта
| Путь | Назначение |
|---|---|
| `data/feeds.json` | RSS-ленты проверенных изданий по темам (редактируется вручную) |
| `data/sources.json` | Списки доверенных доменов (trusted / primary) |
| `data/candidates.json` | Свежие заголовки, пишет `scripts/collect.py` (GitHub Actions). Не править вручную |
| `data/digest.json` | Итоговый дайджест, пишет облачная задача Claude. Демо-версия имеет `"demo": true` |
| `scripts/collect.py` | RSS → `data/candidates.json` (окно 40 ч, только доверенные домены, картинки из RSS); скачивает тексты статей в `data/articles/`, ставит каждой статье `id`, `has_text` и общий `group` для одного события в разных изданиях |
| `data/articles/` | Тексты статей за сегодня (`<id>.txt`), пишет `collect.py`, вчерашние удаляются. Облачная задача читает их, чтобы написать рассказ для читалки |
| `scripts/render.py` | `data/digest.json` → `site/index.html` и `out/digest-DATE.html`; тянет фото, считает метки достоверности |
| `scripts/notify.py` | Одно текстовое сообщение в Telegram (заголовок, до 7 главных, ссылка с параметром против кэша) |
| `scripts/check.py` | Утренняя проверка; при отсутствии свежего дайджеста шлёт сообщение о сбое |
| `templates/digest.html` | Единственный HTML-шаблон (истории, плитки тем, озвучка, тема светлая/тёмная) |
| `routine_prompt.md` | Промпт облачной задачи. Задача читает его из репозитория при каждом запуске (в claude.ai лежит только короткий запуск; полная прежняя копия: `~/.claude/backups/prompt-v4.json`) |
| `.github/workflows/` | `collect.yml`, `publish.yml`, `check.yml` |
| `scripts/validate.py` | Проверка `digest.json` перед публикацией (формат, темы, ссылки есть в candidates). Запускается в `publish.yml` |
| `scripts/assemble.py` | Сборка `data/digest.json` из `/tmp/parts/<тема>.json`: обзор без рассказов, `--drop`, `--curious`, `--out`; запускает облачная задача |
| `scripts/check_part.py` | Проверка файла темы субагентом (лимиты, абзацы, ссылки из файла темы, число мелких) |
| `scripts/show_item.py` | Запись дайджеста и тексты её статей для сверки рассказа (`<тема>:<номер>`, `--top N`); шаг 5 промпта |
| `scripts/alert.py` | Сообщение о сбое в Telegram с повторами (Publish `alert`, `run-status.yml`, `notify.py`) |
| `data/run_status.json` | Пишет облачная задача только при сбое (шаг 8 «СБОЙ»); пуш запускает `run-status.yml`, рассылку дайджеста не запускает |
| `scripts/make_handoff.py` | Готовит `handoff/PROMPT-FOR-OTHER-AI.md`: запрос для ChatGPT/любой модели из `routine_prompt.md` + сегодняшние заголовки |
| `handoff/` | Файл-запрос для других ИИ, обновляется каждую ночь в `collect.yml` |
| `data/engine.json` | Какой движок сейчас пишет дайджест (claude или codex), читается `check.py` |
| `docs/` | SWITCH-TO-CODEX, SWITCH-TO-CLAUDE, ENGINES, STATUS, ARCHITECTURE, OPERATIONS, DECISIONS, ROADMAP, SETUP-VSCODE |

## Смена редактора дайджеста (Claude ⇄ Codex)
«Редактор» — это ИИ, который каждое утро пишет `data/digest.json`. Сейчас он записан в `data/engine.json` (`claude` или `codex`).

**Если владелец говорит что-то вроде «переключись на Codex», «пусть дайджест ведёт Codex», «переключись на Claude», «ты теперь главный», «вернись на Claude»: это команда сменить редактора.** Сделайте так:
1. Откройте `data/engine.json` и узнайте, кто главный сейчас. Если владелец просит того же, кто уже главный, скажите об этом и ничего не меняйте.
2. Если просят Codex: выполните `docs/SWITCH-TO-CODEX.md` пошагово. Если просят Claude: выполните `docs/SWITCH-TO-CLAUDE.md`. Остановитесь на шагах, где нужно действие владельца (поставить прежнего редактора на паузу, подтвердить), и подождите ответа.
3. Не пропускайте шаг «остановить прежнего редактора»: двое одновременно перезапишут друг друга и пришлют в Telegram дубль.
4. Закончив, обновите `data/engine.json` и `docs/STATUS.md` и скажите владельцу, что именно теперь работает и как проверить.
Владельцу не нужно помнить детали: ему достаточно сказать любому из агентов одну из фраз выше. Не начинайте смену по собственной инициативе без такой просьбы.

## Поток данных (UTC, зимнее время Польши = UTC+1)
03:00 `collect.yml` собирает заголовки → 05:12 (06:12 Варшава) облачная задача Claude читает `candidates.json`, пишет `digest.json`, пушит в `main` → пуш запускает `publish.yml` (сборка, GitHub Pages, Telegram) → 06:15 UTC `check.yml` проверяет результат. Подробности в `docs/ARCHITECTURE.md`.

## Правила работы
1. Язык общения с владельцем: русский. Тексты интерфейса и дайджеста только по-русски.
2. Никогда не печатайте и не коммитьте токены, пароли, ID чатов. Секреты лежат только в GitHub → Settings → Secrets and variables → Actions (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`). Если токен утёк: BotFather `/revoke`.
3. Платные API не добавлять без явного согласия. Любой LLM-шаг должен укладываться в подписку или бесплатные лимиты.
4. Облачная задача Claude работает без человека: ей нельзя WebSearch и WebFetch (запросы на подтверждение зависают). Всё сырьё приходит из `candidates.json`. Не возвращайте веб-поиск в промпт без обсуждения.
5. Достоверность важнее полноты: ничего не выдумывать, ссылки только из `candidates.json`, для политики два независимых издания либо пометка «одно издание» и важность ≤2.
6. `routine_prompt.md` читает сама облачная задача: в claude.ai лежит короткий запуск («клонируй, прочитай routine_prompt.md, выполни»), копию править не нужно. Изменили файл, значит изменили поведение задачи со следующего запуска; правки промпта делайте осторожно и проверяйте пробным запуском. Якоря для `make_handoff.py` не переименовывать.
7. Менять `data/digest.json` вручную можно только для тестов, и потом вернуть (`git checkout data/digest.json`). Продакшн-файл перезаписывает задача Claude, и пуш в `main` запускает рассылку в Telegram.
8. Пуш в `main` запускает `publish.yml` и рассылку. Перед пушем скриптов и шаблона проверяйте локально (команды ниже). Мелкие правки можно пушить в `main`, большие лучше через ветку.
9. Сеть: из песочниц ИИ сайты новостей обычно недоступны (403/DNS). Сетевые части (RSS, og:image, Telegram) проверяются только на GitHub Actions у владельца. Не заявляйте, что они работают, пока не видели лог запуска.
10. Из среды Claude Code `git push` может молча зависнуть (ждёт учётные данные). Запускайте `GIT_TERMINAL_PROMPT=0 timeout 60 git push`; чтение (`git ls-remote`) при этом работает.
11. Тестовые ветки `claude/*` удаляйте командой `git push origin --delete <имя>`; на GitHub в `main` остаётся единственная ветка.
12. Читалка: читатель не открывает сайты изданий (их блокируют), поэтому поле `body` в `digest.json` это полный рассказ по-русски, а кнопка «Читать» есть только у новостей с `body`. Платные издания (nytimes, wsj, ft, economist, bloomberg, washingtonpost) без текста: только заголовок и описание как подтверждение события. Мелкие новости темы идут с `"minor": true` (плитки «Также интересно»), основных в теме до 5 (как в routine_prompt.md, check_part.py и validate.py).
13. Макет и снимки: `DIGEST_FILE=<json> NO_NETWORK=1 PLACEHOLDER_IMAGES=1 python scripts/render.py` строит `out/preview-<имя>.html` (папка `out/` не в git). Безголовый Chrome из Bash молча не пишет снимок, если у владельца открыт обычный Chrome: запускать через PowerShell `Start-Process chrome.exe` с `--headless=new`, отдельным `--user-data-dir`, `--window-size=500,H` и страницей в `iframe` шириной 393 px.
14. Пуш в `main` без изменения `data/digest.json` рассылку не запускает (`publish.yml` срабатывает только по этому файлу). Тестовый воркфлоу на ветке, сохраняющий результат коммитом, делает `git push origin HEAD:<ветка>` без `git pull --rebase`.
15. 🔥 и порядок новостей считает `scripts/render.py` по охвату (издания в группах `candidates.json`, порог 3, потолок 5); ИИ ставит только importance 1–2. `routine_prompt.md` читает сама задача из репозитория при каждом запуске.
16. `RemoteTrigger update` с большим телом (~14 КБ) обрывается: держите промпт в репозитории, а в самой задаче только короткий запуск. Правки Python через heredoc с `` дают символ backspace: используйте Edit.
17. `scripts/split_topics.py` режет `data/candidates.json` на файлы по темам в `/tmp/topics`: его запускает сама облачная задача (шаг 1 и пункт 4а `routine_prompt.md`), субагенты читают свой файл, а не весь сырьевой. При сбое скрипта субагенты читают целый `candidates.json`. Пути и формат менять только вместе с `routine_prompt.md`.
18. После теста на подменённом сырье возвращайте `candidates.json` ТОЙ версии, по которой собран `digest.json` (не последней: поздние Collect её заменяют), иначе `validate.py` в Publish падает. Повторная публикация возможна только коммитом, меняющим `data/digest.json`.
19. `git push` без входа в GitHub (Credential Manager) молча не проходит: после пуша сверяйте `git ls-remote origin main` и `git rev-parse HEAD`. Python на ПК не в PATH сессии: `C:\Users\Professional\AppData\Local\Programs\Python\Python315\python.exe`.
20. Облачная задача собирает итог через `scripts/assemble.py`, субагенты проверяют свой файл `scripts/check_part.py`; формат частей (`items`, `curious_candidates` с `body`) и ключ `rows` в `/tmp/topics/<id>.json` менять только вместе с `routine_prompt.md`. Поля строк: `roundup` (рассылка/подборка/live-лента, ставит `collect.py`), `prev` (ссылка была в прошлом дайджесте, ставит `split_topics.py` по `data/digest.json` в клоне); `assemble.py` пишет в дайджест `candidates_generated_at`, по нему `validate.py` в Publish решает, сверять ли ссылки (см. `docs/AUDIT-NOTES.md`).
21. Журнал облачной задачи читается из сессии: `RemoteTrigger` `list_runs` и `get_run_log` (последние 200 событий, старые через `cursor`).

22. Облачная задача: `assemble.py` удаляет служебные поля частей (`note`, `independent`, `skipped`), поэтому оговорки «одно издание» и противоречия источников пишутся в `summary` или `body`. `assemble.py --out` завершается кодом 2, если нет файла темы; тема без материала записывается как `{"items": [], "skipped": "..."}`; в конце печатается строка `METRICS` (число новостей, объём `body`, снятые дубли, неиспользованные `curious`).
23. Перед работой `git fetch` и `git pull --rebase`: Collect коммитит данные в `main`, локальный `main` отстаёт. `AGENTS.md` хранится с CRLF: правка Python `read_text`/`write_text` превращает файл в LF и даёт diff на весь файл; править инструментом Edit или побайтово.
24. Страница: `render.py` кладёт картинки в `site/img/<хеш>.<ext>`, в `site/index.html` относительные ссылки (≈1 МБ); `out/digest-DATE.html` остаётся с data-URI. Шаблон и `externalize_images` менять только вместе.
25. Группы: `collect.py` `group_rows` режет разреженные группы (`split_chain`, плотность <0.5, от 5 строк) и не берёт подборки и обзоры (`NOGROUP_RE`). Менять только с проверкой на сохранённом сырье (`git show <коммит>:data/candidates.json`).
26. Статус GitHub без входа: публичный API `api.github.com/repos/skeptplik/daily-digest/actions/runs` и `/runs/<id>/jobs` (успех Publish и шага Telegram); `gh` на ПК нет. Регулярки в `.py` править только инструментом Edit (`\b` через `sed`/heredoc ломается).
## Локальная проверка (Python 3.12, `pip install -r requirements.txt`)
```
python -m py_compile scripts/*.py
NO_NETWORK=1 PLACEHOLDER_IMAGES=1 python scripts/render.py   # на Windows: set NO_NETWORK=1 && set PLACEHOLDER_IMAGES=1 && python scripts/render.py
python -m json.tool data/digest.json > /dev/null
```
Результат: `site/index.html` (открыть в браузере, ширина 393 px как у Poco F6 Pro). JS шаблона: вытащить самый длинный `<script>` из `site/index.html` и проверить `node --check`.
Без сети и без секретов `notify.py` и `check.py` просто сообщают об отсутствии секретов.

## Что известно как не проверенное
Смотрите `docs/STATUS.md`, раздел «Открытые вопросы». Главное: фото из RSS на реальных лентах, качество русского голоса озвучки на телефоне, первые плановые запуски по расписанию.
