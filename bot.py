# bot.py
import asyncio
import concurrent.futures
import logging
import os

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler
from telegram.ext.filters import COMMAND, TEXT
from uvicorn import Config, Server

# =========================
# Переменные окружения
# =========================
tgkey = os.getenv("TGKEY")
chatID = os.getenv("CHATID")
api_key = os.getenv("GEMINI_KEY")
ci_secret = os.getenv("CI_SECRET")

# =========================
# Настройка логов
# =========================
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

# =========================
# Импорт модулей
# =========================
try:
    from bot_server import create_bot_server
    from gpt import gpt
    from system_report import main as report
except ImportError as e:
    print(
        f"Error importing modules: {e}. Make sure the files are in the correct directory."
    )
    exit()


# =========================
# Telegram bot logic
# =========================
class Main:
    def __init__(self):
        self.lana_command_active = False

    async def start(self, update: Update, context) -> None:
        self.lana_command_active = False
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Привет {update.effective_user.first_name}, Бот запущен.\nВыбери режим работы бота: /chat или /status",
        )

    async def lana(self, update: Update, context) -> None:
        self.lana_command_active = True
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Тебя приветствует ассистент."
        )

    async def status(self, update: Update, context) -> None:
        self.lana_command_active = False
        try:
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                message = await loop.run_in_executor(
                    pool, lambda: asyncio.run(report(tgkey, chatID))
                )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=str(message),
                parse_mode="Markdown",
            )
            logging.info("Отчёт успешно отправлен.")
        except Exception as e:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="Произошла ошибка при отчёте."
            )
            logging.error(f"Ошибка в system_report: {str(e)}")

    async def echo_message(self, update: Update, context) -> None:
        user = update.effective_user.first_name
        text = update.message.text
        logging.info(f"Пользователь {user} написал: {text}")

        if self.lana_command_active:
            try:
                loop = asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    gpt_answer = await loop.run_in_executor(
                        executor, gpt, text, api_key, user
                    )
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, text=str(gpt_answer)
                )
                logging.info(f"Ответ GPT: {gpt_answer}")
            except Exception as e:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, text="Ошибка в GPT."
                )
                logging.error(f"Ошибка в GPT: {str(e)}")
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="Выбери режим: /chat или /status"
            )
            logging.info("Получено сообщение вне активного режима.")


# =========================
# Запуск FastAPI и Telegram
# =========================
async def run_fastapi():
    app = create_bot_server(tg_token=tgkey, chat_id=chatID, ci_secret=ci_secret)
    config = Config(app=app, log_level="info")
    server = Server(config)
    await server.serve()


def main_func():
    application = ApplicationBuilder().token(tgkey).build()
    main_handler = Main()

    handlers = [
        CommandHandler("start", main_handler.start),
        CommandHandler("chat", main_handler.lana),
        CommandHandler("status", main_handler.status),
        MessageHandler(TEXT & (~COMMAND), main_handler.echo_message),
    ]

    for handler in handlers:
        application.add_handler(handler)

    async def runner():
        await asyncio.gather(
            run_fastapi(),  # FastAPI сервер
            application.run_polling(),  # Telegram polling
        )

    asyncio.run(runner())


if __name__ == "__main__":
    try:
        main_func()
    except Exception as e:
        logging.error(f"Неизвестная ошибка: {str(e)}")
        print("Что-то пошло не так. Проверь журнал.")
