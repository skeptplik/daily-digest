# AGENTS.md — daily-digest

Инструкция для ИИ-агентов (Codex, Claude Code и других), работающих в этой папке. Люди: начните с `docs/SETUP-VSCODE.md`.

## Что это
Личный ежедневный новостной дайджест на русском для одного читателя (владелец GitHub `skeptplik`, репозиторий `skeptplik/daily-digest`, ветка `main`). Каждое утро (Польша, Europe/Warsaw) приходит одно сообщение в Telegram со ссылкой на красивую мобильную страницу в стиле историй; такой же файл скачивается на Windows-компьютер в `C:\Digests`.
Платных API нет и не планируется: LLM-шаг выполняет облачная задача Claude по подписке Pro.

## Карта проекта
| Путь | Назначение |
|---|---|
| `data/feeds.json` | RSS-ленты проверенных изданий по темам (редактируется вручную) |
| `data/sources.json` | Списки доверенных доменов (trusted / primary) |
| `data/candidates.json` | Свежие заголовки, пишет `scripts/collect.py` (GitHub Actions). Не править вручную |
| `data/digest.json` | Итоговый дайджест, пишет облачная задача Claude. Демо-версия имеет `"demo": true` |
| `scripts/collect.py` | RSS → `data/candidates.json` (окно 40 ч, только доверенные домены, картинки из RSS) |
| `scripts/render.py` | `data/digest.json` → `site/index.html` и `out/digest-DATE.html`; тянет фото, считает метки достоверности |
| `scripts/notify.py` | Одно текстовое сообщение в Telegram (заголовок, до 7 главных, ссылка с параметром против кэша) |
| `scripts/check.py` | Утренняя проверка; при отсутствии свежего дайджеста шлёт сообщение о сбое |
| `templates/digest.html` | Единственный HTML-шаблон (истории, плитки тем, озвучка, тема светлая/тёмная) |
| `routine_prompt.md` | Источник правды для промпта облачной задачи. Копия живёт ВНУТРИ задачи в claude.ai (см. docs/OPERATIONS.md) |
| `local/` | Скрипты Windows: `Install-Task.ps1`, `Get-Digest.ps1` |
| `.github/workflows/` | `collect.yml`, `publish.yml`, `check.yml` |
| `docs/` | STATUS, ARCHITECTURE, OPERATIONS, DECISIONS, ROADMAP, SETUP-VSCODE |

## Поток данных (UTC, зимнее время Польши = UTC+1)
03:00 `collect.yml` собирает заголовки → 05:12 (06:12 Варшава) облачная задача Claude читает `candidates.json`, пишет `digest.json`, пушит в `main` → пуш запускает `publish.yml` (сборка, GitHub Pages, Telegram) → 06:15 UTC `check.yml` проверяет результат → 06:30 по часам ПК задача Windows скачивает файл. Подробности в `docs/ARCHITECTURE.md`.

## Правила работы
1. Язык общения с владельцем: русский. Тексты интерфейса и дайджеста только по-русски.
2. Никогда не печатайте и не коммитьте токены, пароли, ID чатов. Секреты лежат только в GitHub → Settings → Secrets and variables → Actions (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`). Если токен утёк: BotFather `/revoke`.
3. Платные API не добавлять без явного согласия. Любой LLM-шаг должен укладываться в подписку или бесплатные лимиты.
4. Облачная задача Claude работает без человека: ей нельзя WebSearch и WebFetch (запросы на подтверждение зависают). Всё сырьё приходит из `candidates.json`. Не возвращайте веб-поиск в промпт без обсуждения.
5. Достоверность важнее полноты: ничего не выдумывать, ссылки только из `candidates.json`, для политики два независимых издания либо пометка «одно издание» и важность ≤2.
6. Изменили `routine_prompt.md`: скажите владельцу, что промпт нужно обновить и в самой задаче (она не читает файл из репозитория).
7. Менять `data/digest.json` вручную можно только для тестов, и потом вернуть (`git checkout data/digest.json`). Продакшн-файл перезаписывает задача Claude, и пуш в `main` запускает рассылку в Telegram.
8. Пуш в `main` запускает `publish.yml` и рассылку. Перед пушем скриптов и шаблона проверяйте локально (команды ниже). Мелкие правки можно пушить в `main`, большие лучше через ветку.
9. Сеть: из песочниц ИИ сайты новостей обычно недоступны (403/DNS). Сетевые части (RSS, og:image, Telegram) проверяются только на GitHub Actions у владельца. Не заявляйте, что они работают, пока не видели лог запуска.

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
