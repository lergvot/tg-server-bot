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

        defaults = {
            "project": "<неизвестный проект>",
            "workflow": "<неизвестный workflow>",
            "author": "<неизвестный автор>",
            "branch": "<неизвестная ветка>",
            "status": "<нет статуса>",
            "commit": "<нет коммита>",
            "message": "—",
            "event_name": "<неизвестное событие>",
            "url": "https://example.com",
            "repo_url": "https://example.com",
        }

        project = data.get("project") or defaults["project"]
        workflow = data.get("workflow")
        author = data.get("author") or defaults["author"]
        branch = data.get("branch") or defaults["branch"]
        status = data.get("status") or defaults["status"]
        commit = (data.get("commit") or "")[:7] or defaults["commit"]
        commit_msg = data.get("message") or defaults["message"]
        if isinstance(commit_msg, str):
            commit_msg = commit_msg.strip()
        event_name = data.get("event_name") or defaults["event_name"]

        url = data.get("url") or defaults["url"]
        repo_url = data.get("repo_url") or defaults["repo_url"]

        text = (
            f"🛰 *CI-деплой завершён!*\n\n"
            f"*📦 Проект:* `{project}`\n"
            f"*🛠 Workflow:* `{workflow}`\n"
            f"*👤 Автор:* {author}\n"
            f"*🌿 Ветка:* `{branch}`\n"
            f"*📊 Статус:* {status}\n"
            f"*🔢 Коммит:* `{commit}`\n"
            f"*📝 Сообщение:* {commit_msg}\n"
            f"*⚙️ Событие:* `{event_name}`"
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
