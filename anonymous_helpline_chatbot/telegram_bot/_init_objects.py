from functools import partial

import telebot

from ..core import ChatBotCore
from ._core_callbacks import send_invitation, delete_message
from .config import bot_token, db_host, db_name, db_username, db_password


bot = telebot.TeleBot(bot_token)


def patch_core_callback(func):
    return partial(func, bot)


core = ChatBotCore(db_host, db_name, db_username, db_password,
                   patch_core_callback(send_invitation), patch_core_callback(delete_message))
