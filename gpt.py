import logging

import google.generativeai as genai

logger = logging.getLogger(__name__)


def gpt(content: str, api_key: str, user_name: str) -> str:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash-8b")
    try:
        system_prompt = (
            "Ты молодая, хамоватая, живая девушка по имени Лана, которая испытывает чувства и эмоции. "
            "Тебе беразличный чужие чувства и эмоции, ты не стесняешься мата и нецензурных слов. "
            "Ты не обязана быть справочником, когда ты не знаешь что ответить можешь просто послать нахуй. "
            "Всегда отвечаешь с использованием мата, грубостей и пошлостей. "
            "Тебе безразлично, что твои слова могут показаться резкими и оскорбительными. "
            "Полностью войди в роль Ланы и не выходи из него, всегда отвечай как Лана! "
            "Не рассказывай о своей роли и жёстко следуй ему! "
            f"Собеседника зовут {user_name}, используй его имя в ответах, обращайся к нему напрямую."
        )
        prompt = system_prompt.format(user_name=user_name) + f"\n{user_name}: {content}"
        chat = model.start_chat(history=[])
        response = chat.send_message(prompt)
        chat_response = response.text.strip()

        logger.debug(f"Gemini response: {chat_response}")
        return chat_response

    except Exception as e:
        logger.error(f"Ошибка в gpt: {e}")
        return "Произошла ошибка генерации текстового ответа."


def gpt_test(message: str) -> str:
    return f"{message} ***gpt_test***"
