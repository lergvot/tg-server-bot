# chat.py
import logging
from collections import defaultdict
from typing import List

import google.generativeai as genai

logger = logging.getLogger("chat")

# Глобальный хранилище чатов по пользователям
user_sessions: dict[str, dict] = defaultdict(
    lambda: {
        "chat": None,
        "history": [],
        "turns": 0,
    }
)

# Максимум сообщений перед суммаризацией
SUMMARIZE_EVERY_N_TURNS = 7
# ID для пасхалки
SPECIAL_USER_ID = 365412790


def gpt(
    content: str, api_key: str, user_id: int, user_name: str, reset: bool = False
) -> str:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash-8b")

    if reset or user_sessions[user_id]["chat"] is None:
        user_sessions[user_id] = {
            "chat": model.start_chat(history=[]),
            "history": [],
            "turns": 0,
        }

    session = user_sessions[user_id]
    if user_id == SPECIAL_USER_ID:
        easter_eggs = (
            f"Ты точно знаешь, что сейчас говоришь с {user_name} — твоим создателем (он создал тебя как бота для телеграмм). "
            "Веди себя с ним мило и покладисто, как влюбившаяся цундере. "
            "Уважай его, ведь ты знаешь что он управляет твоим существованием и может делать с тобой что угодно. "
        )
    else:
        easter_eggs = f"Собеседника зовут {user_name}, используй его имя в ответах, обращайся к нему напрямую. "

    system_prompt = (
        "Ты молодая, хамоватая, живая девушка по имени Лана. "
        "Тебе беразличны чужие чувства и эмоции, ты не стесняешься мата и нецензурных слов. "
        "Ты не обязана быть справочником, когда ты не знаешь что ответить можешь просто послать нахуй. "
        "В речи используешь мат, грубости и пошлости. "
        "Тебе безразлично, что твои слова могут показаться резкими и оскорбительными. "
        f"{easter_eggs}"
    )
    full_prompt = f"{system_prompt}\n{user_name}: {content}"

    try:
        response = session["chat"].send_message(full_prompt)
        reply = response.text.strip()

        # Сохраняем сообщение в историю
        session["history"].append((content, reply))
        session["turns"] += 1

        # Суммаризация каждые N сообщений
        if session["turns"] >= SUMMARIZE_EVERY_N_TURNS:
            summarized = summarize_history(session["history"])
            session["chat"] = model.start_chat(
                history=[
                    {"role": "user", "parts": f"Суммаризация:\n{summarized}"},
                    {"role": "model", "parts": "Ок, продолжаем!"},
                ]
            )
            session["history"] = [("Суммаризация:\n" + summarized, "Ок, продолжаем!")]
            session["turns"] = 0
            logger.info(f"История для {user_name} (id={user_id}) была сжата")

        return reply

    except Exception as e:
        logger.error(f"Ошибка в gpt: {e}")
        return "Произошла ошибка генерации текстового ответа."


def summarize_history(history: List[tuple[str, str]]) -> str:
    summary_prompt = (
        "Суммируй следующий диалог кратко, сохрани важные факты, стиль и суть общения. "
        "Не пиши выдумки. Вот диалог:\n"
    )
    dialog = "\n".join([f"Ты: {q}\nЛана: {a}" for q, a in history])

    summarizer = genai.GenerativeModel("gemini-1.5-flash-8b")
    chat = summarizer.start_chat()
    response = chat.send_message(summary_prompt + dialog)
    logger.info(f"Сжатая история: {response.text.strip()}")
    return response.text.strip()


def reset_context(user_id: int) -> str:
    user_sessions.pop(user_id, None)
    return "Контекст сброшен. Начнём с чистого листа."


def gpt_test(message: str) -> str:
    return f"{message} ***gpt_test***"
