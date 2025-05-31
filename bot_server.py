# bot_server.py
from fastapi import FastAPI, Request, HTTPException
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup


def create_bot_server(tg_token: str, chat_id: str, ci_secret: str) -> FastAPI:
    """Создаёт FastAPI-приложение, которое обрабатывает CI webhook."""
    app = FastAPI()
    bot = Bot(token=tg_token)

    @app.post("/ci-report")
    async def ci_report(request: Request):
        data = await request.json()
        if data.get("secret") != ci_secret:
            raise HTTPException(status_code=403, detail="Forbidden")

        project = data.get("project")
        status = data.get("status")
        commit = data.get("commit", "")[:7]
        url = data.get("url")
        repo_url = data.get("repo_url")

        if not all([project, status, url, repo_url]):
            raise HTTPException(status_code=400, detail="Missing fields")

        text = (
            f"🛰 *CI-деплой завершён!*\n\n"
            f"📦 *Проект:* {project}\n"
            f"🔢 *Коммит:* `{commit}`\n"
            f"📊 *Статус:* {status}"
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
