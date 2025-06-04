import asyncio
import concurrent.futures
import logging
import os
import threading

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from uvicorn import Config, Server

from version import version

logger = logging.getLogger(__name__)

# Проверка переменных окружения
required_env_vars = {
    "TGKEY": os.getenv("TGKEY"),
    "CHATID": os.getenv("CHATID"),
    "GEMINI_KEY": os.getenv("GEMINI_KEY"),
    "CI_SECRET": os.getenv("CI_SECRET"),
}
missing_vars = [k for k, v in required_env_vars.items() if not v]
if missing_vars:
    raise RuntimeError(f"Не заданы переменные окружения: {', '.join(missing_vars)}")

tgkey = required_env_vars["TGKEY"]
chatID = required_env_vars["CHATID"]
api_key = required_env_vars["GEMINI_KEY"]
ci_secret = required_env_vars["CI_SECRET"]


# Настройка логов
cwd = os.path.dirname(os.path.abspath(__file__))
log_path = os.path.join(cwd, "tg_bot.log")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    filename=log_path,
    encoding="utf-8",
)

httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)

# Импорт модулей
try:
    from CI_report import create_bot_server
    from gpt import gpt
    from system_report import main as report
except ImportError as e:
    logger.error(f"Ошибка импорта модулей: {e}")
    exit(1)


# Telegram bot logic
class Main:
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        context.user_data["lana"] = False
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Привет {update.effective_user.first_name}, Бот версии {version} запущен.\nВыбери режим работы: /chat или /status",
        )

    async def lana(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        context.user_data["lana"] = True
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Тебя приветствует ассистент."
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        context.user_data["lana"] = False
        try:
            message = await report(tgkey, chatID)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=str(message),
                parse_mode="Markdown",
            )
            logger.info("Отчёт успешно отправлен.")
        except Exception as e:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="Произошла ошибка при отчёте."
            )
            logger.error(f"Ошибка в system_report: {str(e)}")

    async def echo_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user.first_name
        text = update.message.text
        logger.info(f"Пользователь {user} написал: {text}")

        if context.user_data.get("lana"):
            try:
                loop = asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    gpt_answer = await loop.run_in_executor(
                        executor, gpt, text, api_key, user
                    )
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, text=str(gpt_answer)
                )
                logger.info(f"Ответ GPT: {gpt_answer}")
            except Exception as e:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, text="Ошибка в GPT."
                )
                logger.error(f"Ошибка в GPT: {str(e)}")
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="Выбери режим: /chat или /status"
            )
            logger.info("Получено сообщение вне активного режима.")


# Запуск FastAPI и Telegram
async def run_fastapi():
    app = create_bot_server(tg_token=tgkey, chat_id=chatID, ci_secret=ci_secret)
    config = Config(app=app, host="127.0.0.1", port=8001, log_level="info")
    server = Server(config)
    await server.serve()


def start_fastapi():
    asyncio.run(run_fastapi())


def main_func():
    fastapi_thread = threading.Thread(target=start_fastapi, daemon=True)
    fastapi_thread.start()

    application = ApplicationBuilder().token(tgkey).build()
    main_handler = Main()

    application.add_handler(CommandHandler("start", main_handler.start))
    application.add_handler(CommandHandler("chat", main_handler.lana))
    application.add_handler(CommandHandler("status", main_handler.status))
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), main_handler.echo_message)
    )

    application.run_polling()


if __name__ == "__main__":
    try:
        main_func()
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {str(e)}")
