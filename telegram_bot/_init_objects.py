import telebot

from ..core import ChatBotCore
from .config import bot_token, db_host, db_name, db_username, db_password


core = ChatBotCore(db_host, db_name, db_username, db_password)

bot = telebot.TeleBot(bot_token)
