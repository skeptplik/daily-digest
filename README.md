# daily-digest

Личный ежедневный новостной дайджест на русском: красивая мобильная страница в стиле историй, одно сообщение в Telegram со ссылкой, копия на Windows в `C:\Digests`.

Как работает: GitHub Actions собирает свежие заголовки из RSS проверенных изданий → облачная задача Claude (Sonnet 5.5, по подписке, без API) выбирает главное и пишет `data/digest.json` → Actions собирает страницу, публикует на GitHub Pages и шлёт сообщение в Telegram → проверка сбоя → задача Windows скачивает файл.

Страница: https://skeptplik.github.io/daily-digest/

## Документы
- `docs/SETUP-VSCODE.md`: как начать работу в папке (VS Code, Claude Code, Codex)
- `docs/STATUS.md`: что работает, результаты тестов, открытые вопросы
- `docs/ARCHITECTURE.md`: схема, расписание, форматы данных
- `docs/OPERATIONS.md`: облачная задача, GitHub, Windows, Telegram, поломки
- `docs/DECISIONS.md`: решения и предпочтения владельца
- `docs/ROADMAP.md`: планы
- `AGENTS.md` / `CLAUDE.md`: правила для ИИ-агентов
- `ИНСТРУКЦИЯ.md`: первоначальная пошаговая установка (частично устарела, актуальное расписание и схема в `docs/`)

Секреты (Settings → Secrets and variables → Actions): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
