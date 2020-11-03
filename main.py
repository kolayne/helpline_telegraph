from functools import wraps
from sys import stderr
from traceback import format_exc

import telebot
from typing import Callable

from config import bot_token


class AnyContentType:
    def __contains__(self, item): return True


bot = telebot.TeleBot(bot_token)


def nonfalling_handler(func: Callable):
    @wraps(func)
    def ans(message: telebot.types.Message, *args, **kwargs):
        try:
            func(message, *args, **kwargs)
        except:
            try:
                s = "Произошла ошибка"
                try:
                    bot.send_message(405017295, format_exc())
                except:
                    s += ". Свяжитесь с @kolayne для исправления"
                else:
                    s += ". @kolayne получил уведомление о ней"
                try:
                    s += ". Технические детали:\n```" + format_exc() + "```"
                    print(format_exc(), file=stderr)
                    bot.send_message(405017295, format_exc())
                except:
                    pass

                bot.send_message(message.chat.id, s)
            except:
                print(format_exc(), file=stderr)

    return ans


@bot.message_handler(commands=['start', 'help'])
@nonfalling_handler
def hello(message: telebot.types.Message):
    bot.reply_to(message, "Привет. /start_conversation, чтобы начать беседу, /end_conversation чтобы завершить")

@bot.message_handler(commands=['start_conversation'])
def start_conversation(message: telebot.types.Message):
    raise NotImplementedError()
    bot.reply_to(message, "Началась беседа с оператором. Отправьте сообщение, и оператор его увидит")

@bot.message_handler(commands=['end_conversation'])
def end_conversation(message: telebot.types.Message):
    raise NotImplementedError()
    bot.reply_to(message, "Беседа с оператором прекратилась")

@bot.message_handler(func=lambda message: "conversation has not started")
def conversation_not_started(message: telebot.types.Message):
    bot.reply_to(message, "Чтобы начать общаться с оператором, нужно написать /start_conversation")

@bot.message_handler(content_types=['text'])
@nonfalling_handler
def text_message(message: telebot.types.Message):
    raise NotImplementedError()

@bot.message_handler(content_types=['photo', 'video'])
@nonfalling_handler
def photo_or_video_message(message: telebot.types.Message):
    if message.media_group_id is not None:
        bot.reply_to(message, "Отправка групп медиа не поддерживается. Они будут отправлены как отдельные сообщения")

    raise NotImplementedError()

@bot.message_handler(content_types=AnyContentType())
@nonfalling_handler
def another_content_type(message: telebot.types.Message):
    bot.reply_to(message, "Сообщения этого типа не поддерживаются. Свяжитесь с @kolayne, чтобы добавить поддержку")


if __name__ == "__main__":
    bot.polling(none_stop=False)
