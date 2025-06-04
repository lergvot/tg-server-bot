# CI_report.py
import logging

from fastapi import FastAPI, HTTPException, Request
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup


def create_bot_server(tg_token: str, chat_id: str, ci_secret: str) -> FastAPI:
    app = FastAPI()
    bot = Bot(token=tg_token)

    logger = logging.getLogger("ci_report")
    logger.setLevel(logging.INFO)

    def get_str_field(data: dict, field: str, fallback: str) -> str:
        value = data.get(field)
        if isinstance(value, str):
            value = value.strip()
            return value or fallback
        return fallback

    @app.get("/health", tags=["system"])
    async def health():
        return {"status": "ok"}

    @app.post("/ci-report", tags=["system"])
    async def ci_report(request: Request):
        data = await request.json()
        if data.get("secret") != ci_secret:
            raise HTTPException(status_code=403, detail="Forbidden")

        project = get_str_field("project", "<неизвестный проект>")
        workflow = get_str_field("workflow", "<неизвестный workflow>")
        author = get_str_field("author", "<неизвестный автор>")
        branch = get_str_field("branch", "<неизвестная ветка>")
        status = get_str_field("status", "<нет статуса>")
        commit = get_str_field("commit", "")[:7] or "<нет коммита>"
        commit_msg = get_str_field("message", "—").splitlines()[0]
        event_name = get_str_field("event_name", "<неизвестное событие>")
        url = get_str_field("url", "https://example.com")
        repo_url = get_str_field("repo_url", "https://example.com")

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

        try:
            await bot.send_message(
                chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения в Telegram: {e}")
            raise HTTPException(status_code=500, detail="Ошибка при отправке сообщения")

        return {"ok": True}

    return app
