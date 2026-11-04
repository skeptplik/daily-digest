# Как начать работу в папке (Visual Studio Code, Claude Code, Codex)

Всё, что нужно, уже лежит в репозитории: достаточно скачать его в папку. Данные и секреты вне репозитория (токен бота, ID чата) нужны только на GitHub, локально они не нужны.

## 1. Установить (один раз)
1. Git for Windows: https://git-scm.com/download/win
2. Python 3.12: https://www.python.org/downloads/ (галочка «Add python.exe to PATH»).
3. Visual Studio Code.
4. По желанию Node.js LTS (только для проверки JS командой `node --check`).
5. Расширения VS Code (VS Code сам предложит из `.vscode/extensions.json`): Python, Claude Code, OpenAI Codex (ChatGPT), GitHub Actions.

## 2. Скачать проект в папку
В PowerShell выберите, где хранить проекты (пример `C:\Projects`), затем:
```
cd C:\Projects
git clone https://github.com/skeptplik/daily-digest.git Digest
cd Digest
```
Если Git спросит вход, войдите в GitHub через окно браузера (Git Credential Manager). Затем:
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
code .
```
Новая папка `Digest` и есть ваш проект. В ней уже есть `AGENTS.md` (для Codex и других), `CLAUDE.md` (для Claude Code, подтягивает `AGENTS.md`) и каталог `docs/`.

## 3. Начать сессию
- **Claude Code** (расширение в VS Code или `claude` в терминале в папке): он сам прочитает `CLAUDE.md`. Первый запрос: «Прочитай docs/STATUS.md и docs/OPERATIONS.md и скажи, что осталось проверить».
- **Codex**: он читает `AGENTS.md`. Тот же первый запрос.
- Можно открывать обоих в одной папке, но не давайте им править одни и те же файлы одновременно и не пушьте без `git pull`.

## 4. Проверка изменений локально (без сети и без секретов)
Задачи VS Code (Terminal → Run Task): «Digest: собрать демо-страницу (без сети)», «Digest: проверить digest.json», «Digest: собрать заголовки (RSS, нужен интернет)».
Вручную:
```
set NO_NETWORK=1
set PLACEHOLDER_IMAGES=1
python scripts/render.py
```
Откройте `site\index.html` в Chrome (F12 → режим телефона, 393 px). `PLACEHOLDER_IMAGES` рисует заглушки вместо фото (настоящие фото грузятся только на GitHub).

## 5. Опубликовать изменения
```
git add -A
git commit -m "Что изменено"
git pull --rebase origin main
git push origin main
```
Пуш в `main`, не затрагивающий `data/digest.json`, рассылку не запускает. Если изменили `scripts/` или `templates/`, пересоберите страницу вручную: GitHub → Actions → Publish digest → Run workflow (придёт новое сообщение в Telegram).

## 6. Что остаётся ВНЕ папки (и где это настроено)
| Что | Где |
|---|---|
| Облачная задача Claude (расписание, модель, режим «Авто», промпт) | claude.ai/code/routines, подробности в `docs/OPERATIONS.md` |
| Интеграция GitHub ↔ Claude (приложение с правом записи) | claude.ai → настройки/коннекторы + страница приложения на GitHub |
| Секреты Telegram | GitHub → Settings → Secrets and variables → Actions |
| GitHub Pages (Source: GitHub Actions) | GitHub → Settings → Pages |
| Telegram-бот | BotFather (токен хранит владелец) |

## 7. Безопасность
Не вставляйте токены в файлы, чаты и скриншоты. Если токен утёк, в BotFather `/revoke`, затем обновить секрет на GitHub.
