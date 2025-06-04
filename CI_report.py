# CI_report.py
from fastapi import FastAPI, HTTPException, Request
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup


def create_bot_server(tg_token: str, chat_id: str, ci_secret: str) -> FastAPI:
    app = FastAPI()
    bot = Bot(token=tg_token)

    @app.post("/ci-report")
    async def ci_report(request: Request):
        data = await request.json()
        if data.get("secret") != ci_secret:
            raise HTTPException(status_code=403, detail="Forbidden")

        def get_value(field: str, fallback: str) -> str:
            value = data.get(field)
            if isinstance(value, str):
                value = value.strip()
                return value or fallback

        project = get_value("project", "<неизвестный проект>")
        workflow = get_value("workflow", "<неизвестный workflow>")
        author = get_value("author", "<неизвестный автор>")
        branch = get_value("branch", "<неизвестная ветка>")
        status = get_value("status", "<нет статуса>")
        commit = get_value("commit", "")[:7] or "<нет коммита>"
        commit_msg = get_value("message", "—").splitlines()[0]
        event_name = get_value("event_name", "<неизвестное событие>")
        url = get_value("url", "https://example.com")
        repo_url = get_value("repo_url", "https://example.com")

        text = (
            f"🛰 <b>CI-деплой завершён!</b>\n\n"
            f"<b>📦 Проект:</b> <code>{project}</code>\n"
            f"<b>🛠 Workflow:</b> <code>{workflow}</code>\n"
            f"<b>👤 Автор:</b> {author}\n"
            f"<b>🌿 Ветка:</b> <code>{branch}</code>\n"
            f"<b>📊 Статус:</b> {status}\n"
            f"<b>🔢 Коммит:</b> <code>{commit}</code>\n"
            f"<b>📝 Сообщение:</b> {commit_msg}\n"
            f"<b>⚙️ Событие:</b> <code>{event_name}</code>"
        )

        buttons = [
            [
                InlineKeyboardButton("🔍 Лог пайплайна", url=url),
                InlineKeyboardButton("📂 Репозиторий", url=repo_url),
            ]
        ]
        markup = InlineKeyboardMarkup(buttons)

        await bot.send_message(
            chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=markup
        )
        return {"ok": True}

    return app
