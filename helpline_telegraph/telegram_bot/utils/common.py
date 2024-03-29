from functools import wraps
from sys import stderr
from traceback import format_exc
from typing import Callable, Union, Any

import telebot

from .._init_objects import bot, core


def notify_admins(**kwargs) -> bool:
    """
    Send a text message to all the bot administrators. Any exceptions occurring inside are suppressed

    :param kwargs: Keyword arguments to be forwarded to `bot.send_message` (must not contain `chat_id`)
    :return: `True` if a message was successfully delivered (i. e. no exception occurred) to at least one admin, `False`
        otherwise
    """
    try:
        admins = core.get_admins_ids()
    except Exception:
        print("Couldn't get admins ids inside of `notify_admins`:", file=stderr)
        print(format_exc(), file=stderr)
        return False

    sent = False

    try:
        for i in admins:
            try:
                bot.send_message(chat_id=i, **kwargs)
            except Exception:
                print("Couldn't send a message to an admin inside of `notify_admins`:", file=stderr)
                print(format_exc(), file=stderr)
            else:
                sent = True

    except Exception:
        print("Something went wrong while **iterating** throw `admins` inside of `notify_admins`:", file=stderr)
        print(format_exc(), file=stderr)

    return sent


def nonfalling_handler(func: Callable) -> Any:
    @wraps(func)
    def ans(message: Union[telebot.types.Message, telebot.types.CallbackQuery], *args, **kwargs):
        try:
            return func(message, *args, **kwargs)
        except Exception:
            try:
                # For callback query handlers
                # (we got a `telebot.types.CallbackQuery` object instead of a `telebot.types.Message` object)
                if hasattr(message, 'message'):
                    message = message.message

                s = "Произошла ошибка"
                if notify_admins(text=('```' + format_exc() + '```'), parse_mode="Markdown"):
                    s += ". Наши администраторы получили уведомление о ней"
                else:
                    s += ". Свяжитесь с администрацией бота для исправления"
                s += ". Технические детали:\n```" + format_exc() + "```"

                print(format_exc(), file=stderr)
                bot.send_message(message.chat.id, s, parse_mode="Markdown")
            except Exception:
                print("An exception while handling an exception:", file=stderr)
                print(format_exc(), file=stderr)

    return ans
