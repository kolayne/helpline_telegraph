from functools import wraps
from sys import stderr
from traceback import format_exc

import telebot
from typing import Callable

from logic import add_user, start_conversation, end_conversation, is_operator, in_conversation_as
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
                    bot.send_message(405017295, '```' + format_exc() + '```', parse_mode="Markdown")
                except:
                    s += ". Свяжитесь с @kolayne для исправления"
                else:
                    s += ". @kolayne получил уведомление о ней"
                try:
                    s += ". Технические детали:\n```" + format_exc() + "```"
                    print(format_exc(), file=stderr)
                except:
                    pass

                bot.send_message(message.chat.id, s, parse_mode="Markdown")
            except:
                print(format_exc(), file=stderr)

    return ans


@bot.message_handler(commands=['start', 'help'])
@nonfalling_handler
def start_help_handler(message: telebot.types.Message):
    bot.reply_to(message, "Привет. /start_conversation, чтобы начать беседу, /end_conversation чтобы завершить")
    add_user(message.chat.id)

@bot.message_handler(commands=['start_conversation'])
@nonfalling_handler
def start_conversation_handler(message: telebot.types.Message):
    operator_id, local_user_id = start_conversation(message.chat.id)
    if operator_id == -1:
        bot.reply_to(message, "Вы уже в беседе с оператором. Используйте /end_conversation чтобы прекратить")
    elif operator_id == -2:
        bot.reply_to(message, "Операторы не могут запрашивать помощь :(\nОбратитесь к @kolayne для реализации такой "
                              "возможности")
    else:
        bot.reply_to(message, "Началась беседа с оператором. Отправьте сообщение, и оператор его увидит. "
                              "Используйте /end_conversation чтобы прекратить")
        bot.send_message(operator_id, f"Пользователь №{local_user_id} начал беседу с вами")

@bot.message_handler(commands=['end_conversation'])
@nonfalling_handler
def end_conversation_handler(message: telebot.types.Message):
    if is_operator(message.chat.id):
        bot.reply_to(message, "Оператор не может прекратить беседу. Обратитесь к @kolayne для реализации такой "
                              "возможности")
        return

    ans = end_conversation(message.chat.id)
    if ans:
        operator_id, local_user_id = ans
        bot.reply_to(message, "Беседа с оператором прекратилась")
        bot.send_message(operator_id, f"Пользователь №{local_user_id} прекратил беседу")
    else:
        bot.reply_to(message, "В данный момент вы ни с кем не беседуете. Используйте /start_conversation чтобы начать")

@bot.message_handler(func=lambda message: not is_operator(message.chat.id) and
                                          in_conversation_as(message.chat.id) is None)
@nonfalling_handler
def conversation_not_started(message: telebot.types.Message):
    bot.reply_to(message, "Чтобы начать общаться с оператором, нужно написать /start_conversation")

@bot.message_handler(content_types=['text'])
@nonfalling_handler
def text_message_handler(message: telebot.types.Message):
    raise NotImplementedError()

@bot.message_handler(content_types=['photo', 'video'])
@nonfalling_handler
def photo_or_video_message_handler(message: telebot.types.Message):
    if message.media_group_id is not None:
        bot.reply_to(message, "Отправка групп медиа не поддерживается. Они будут отправлены как отдельные сообщения")

    raise NotImplementedError()

@bot.message_handler(content_types=AnyContentType())
@nonfalling_handler
def another_content_type_handler(message: telebot.types.Message):
    bot.reply_to(message, "Сообщения этого типа не поддерживаются. Свяжитесь с @kolayne, чтобы добавить поддержку")


if __name__ == "__main__":
    bot.polling(none_stop=False)
