# daily-digest

Ежедневный новостной дайджест в формате историй.

1. В 8:00 облачная задача (routine) Claude собирает новости из проверенных изданий (`data/sources.json`) и пишет `data/digest.json` в ветку main.
2. Workflow `.github/workflows/publish.yml` собирает страницу (`scripts/render.py` + `templates/digest.html`),
   публикует на GitHub Pages и отправляет ссылку и файл в Telegram (`scripts/notify.py`).
3. На Windows `local/Install-Task.ps1` ставит задачу, которая скачивает свежий файл в `C:\Digests` и чистит старые.

Пошаговая инструкция: `ИНСТРУКЦИЯ.md`. Секреты (Settings → Secrets and variables → Actions): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

Файл `data/digest.json` изначально содержит ДЕМО-данные. Первый настоящий запуск заменит их.
