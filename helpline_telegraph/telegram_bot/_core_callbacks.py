from sys import stderr
from traceback import format_exc

import telebot
from typing import Any, Optional

from .utils.tg_callback_shortener import shorten_callback_data_and_jdump


# Invitations

def send_invitation(bot: telebot.TeleBot, operator_chat_id: int, client_chat_id: int,
                    message_text: str) -> Optional[int]:
    keyboard = telebot.types.InlineKeyboardMarkup()
    callback_data = {'type': 'conversation_acceptation', 'client_id': client_chat_id}
    keyboard.add(telebot.types.InlineKeyboardButton("Присоединиться",
                                                    callback_data=shorten_callback_data_and_jdump(callback_data)))
    try:
        return bot.send_message(operator_chat_id, message_text, reply_markup=keyboard).message_id
    except telebot.apihelper.ApiException:
        print("Telegram API Exception while sending out operators invitations:", file=stderr)
        print(format_exc(), file=stderr)

def delete_message(bot: telebot.TeleBot, chat_id: int, message_id: int) -> Any:
    return bot.delete_message(chat_id, message_id)
