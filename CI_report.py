# CI_report.py
import logging

from fastapi import FastAPI, HTTPException, Request
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup


# Глобальная переменная для хранения последнего деплоя
_last_deploy_report = None


def get_last_deploy_report():
    return _last_deploy_report


def create_bot_server(tg_token: str, chat_id: str, ci_secret: str) -> FastAPI:
    app = FastAPI()
    bot = Bot(token=tg_token)

    # Настройка логгера
    logger = logging.getLogger("ci_report")
    if not logger.hasHandlers():
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    def get_str_field(data: dict, field: str, fallback: str) -> str:
        return str(data.get(field, fallback)).strip() or fallback

    def add_status_emoji(status: str) -> str:
        status = status.lower()
        if "success" in status:
            return f"✅ {status}"
        elif "fail" in status or "error" in status:
            return f"❌ {status}"
        return status

    @app.get("/health", tags=["system"])
    async def health():
        return {"status": "ok"}

    @app.post("/ci-report", tags=["system"])
    async def ci_report(request: Request):
        data = await request.json()
        if data.get("secret") != ci_secret:
            logger.warning("Попытка доступа с неверным секретом.")
            raise HTTPException(status_code=403, detail="Forbidden")

        project = get_str_field(data, "project", "<неизвестный проект>")
        workflow = get_str_field(data, "workflow", "<неизвестный workflow>")
        author = get_str_field(data, "author", "<неизвестный автор>")
        branch = get_str_field(data, "branch", "<неизвестная ветка>")
        status = add_status_emoji(get_str_field(data, "status", "<нет статуса>"))
        commit = get_str_field(data, "commit", "")[:7] or "<нет коммита>"
        commit_msg = get_str_field(data, "message", "—")
        commit_msg = (
            commit_msg.replace(":", ":\n", 1) if ":" in commit_msg else commit_msg
        )
        event_name = get_str_field(data, "event_name", "<неизвестное событие>")
        url = get_str_field(data, "url", "https://example.com")
        repo_url = get_str_field(data, "repo_url", "https://example.com")

        text = (
            f"🛰 <b>CI-Отчёт</b>\n\n"
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
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=markup,
            )
            logger.info(f"Отчёт о CI отправлен: {project} | {branch} | {status}")

            # Сохраняем последний деплой в main с успешным статусом
            if branch == "main" and "✅" in status:
                global _last_deploy_report
                _last_deploy_report = text

        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения в Telegram: {e}")
            raise HTTPException(status_code=500, detail="Ошибка при отправке сообщения")

        return {"ok": True}

    return app
