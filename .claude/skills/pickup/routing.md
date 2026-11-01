# Роутинг для проекта Digest (daily-digest)

Общие правила — в `~/.claude/CLAUDE.md`; здесь только подсказки проекта. Они важнее `~/.claude/routing.md`.

## Осторожно (копия/проба, план и «да» пользователя)
- Пуш в `main`, затрагивающий `data/digest.json`: запускает `publish.yml` и рассылку в Telegram. Ручные правки `data/digest.json` — только для тестов, затем `git checkout data/digest.json`.
- `data/candidates.json` пишет Actions; вручную не править.
- Секреты, токены, ID чатов: не выводить и не коммитить.
- `routine_prompt.md`: после правки сказать владельцу, что промпт нужно обновить внутри облачной задачи в claude.ai.
- `.github/workflows/`, `local/*.ps1` (задача Windows, автозапуск): сначала план и «да».
- Платные API и WebSearch/WebFetch в облачной задаче не возвращать.

## Что отдавать Haiku
- `python -m py_compile scripts/*.py`, локальная сборка `render.py` с `NO_NETWORK=1 PLACEHOLDER_IMAGES=1`, `json.tool`, `node --check` скрипта шаблона — с отчётом.
- Поиск по `data/feeds.json` и `data/sources.json`, чтение логов запусков Actions, правки документов по точному тексту.

## Sonnet сам
Логика `scripts/*.py`, шаблон `templates/digest.html`, промпт `routine_prompt.md`, разбор причин сбоев.

## Ограничение окружения
Сетевые части (RSS, og:image, Telegram) отсюда не проверить; «работает» только после лога запуска у владельца.
