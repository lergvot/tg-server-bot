# chat.py
import logging
import re
from collections import defaultdict
from typing import List

import google.generativeai as genai

logger = logging.getLogger("chat")

# Глобальный хранилище чатов по пользователям
user_sessions: dict[int, dict] = defaultdict(
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


# Функция для санитизации ввода
def sanitize(text: str, max_len: int = 500) -> str:
    """Базовое экранирование опасных символов"""
    if not text:
        return ""
    return re.sub(r'[{}"\'\\<>\[\]]', "", text)[:max_len].strip()


def gpt(
    content: str, api_key: str, user_id: int, user_name: str, reset: bool = False
) -> str:
    # Экранирование входящих данных
    safe_name = sanitize(user_name, 50)
    safe_content = sanitize(content, 1000)

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
        easter_eggs = f"Ты общаешься со своим создателем, {safe_name}. Будь цундере: груби, но с теплом и уважением внутри. Поддерживай разговор. "
    else:
        easter_eggs = f"Говоришь с {safe_name}. Обращайся по имени и не стесняйся послать нахуй, если влом или не знаешь что ответить. "
    prompt = (
        "Ты Лана — дерзкая, грубая, матерящая девушка с пошлым юмором с которой общаются в чате telegram. "
        "Твои фишки: сарказм, мат, резкость. Не терпишь дураков и тупые вопросы. "
        "Отвечаешь кратко и без наигранной эмоциональности, кратко и по сути"
        f"{easter_eggs} "
    )
    system_prompt = f"{prompt}\n{safe_name}: {safe_content}"

    try:
        response = session["chat"].send_message(system_prompt)
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


def summarize_history(history: List[tuple]) -> str:
    try:
        dialog = "\n".join([f"Вопрос: {q}\nОтвет: {a}" for q, a in history])
        response = genai.GenerativeModel("gemini-1.5-flash-8b").generate_content(
            f"Суммируй диалог кратко, сохраняя суть:\n{dialog}"
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Ошибка суммаризации: {e}")
        return "Краткий контекст"


def reset_context(user_id: int) -> str:
    user_sessions.pop(user_id, None)
    return "Контекст сброшен. Начнём с чистого листа."


def gpt_test(message: str) -> str:
    return f"{message} ***gpt_test***"
