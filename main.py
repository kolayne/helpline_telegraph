from functools import wraps
from sys import stderr
from traceback import format_exc

import telebot
from typing import Callable

from db_connector import PrettyCursor
from logic import add_user, start_conversation, end_conversation, is_operator_and_is_not_crying, in_conversation_as,\
    get_operator_id
from config import bot_token


class AnyContentType:
    def __contains__(self, item): return True


bot = telebot.TeleBot(bot_token)


def nonfalling_handler(func: Callable):
    @wraps(func)
    def ans(message: telebot.types.Message, *args, **kwargs):
        try:
            func(message, *args, **kwargs)
        except Exception:
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
        bot.reply_to(message, "Операторы не могут запрашивать помощь, пока помогают кому-то\nОбратитесь к @kolayne для "
                              "реализации такой возможности")
    else:
        bot.reply_to(message, "Началась беседа с оператором. Отправьте сообщение, и оператор его увидит. "
                              "Используйте /end_conversation чтобы прекратить")
        bot.send_message(operator_id, f"Пользователь №{local_user_id} начал беседу с вами")

@bot.message_handler(commands=['end_conversation'])
@nonfalling_handler
def end_conversation_handler(message: telebot.types.Message):
    if is_operator_and_is_not_crying(message.chat.id):
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

@bot.message_handler(content_types=['text'])
@nonfalling_handler
def text_message_handler(message: telebot.types.Message):
    user_in_conversation_type = in_conversation_as(message.chat.id)

    if user_in_conversation_type is None:
        bot.reply_to(message, "Чтобы начать общаться с оператором, нужно написать /start_conversation")
        return

    if user_in_conversation_type == 'operator':
        if message.reply_to_message is None:
            bot.reply_to(message, "Операторы должен отвечать на сообщения. Нельзя написать сообщение просто так")
            return

        with PrettyCursor() as cursor:
            cursor.execute("SELECT sender_chat_id, sender_message_id FROM reflected_messages WHERE receiver_chat_id=%s "
                           "AND receiver_message_id=%s",
                           (message.reply_to_message.chat.id, message.reply_to_message.message_id))
            try:
                chat_id, message_id = cursor.fetchone()
            except TypeError:
                bot.reply_to(message, "Не похоже, что сообщение, на которое вы ответили, пришло от вашего собеседника")
                return

        sent = bot.send_message(chat_id, message.text, reply_to_message_id=message_id)
    elif user_in_conversation_type == 'client':
        if message.reply_to_message is not None:
            pass

        sent = bot.send_message(get_operator_id(message.chat.id), message.text)
    else:
        raise NotImplementedError("Unknown `user_in_conversation_type`")

    with PrettyCursor() as cursor:
        cursor.execute("INSERT INTO reflected_messages(sender_chat_id, sender_message_id, receiver_chat_id, "
                       "receiver_message_id) VALUES (%s, %s, %s, %s)",
                       (message.chat.id, message.message_id, sent.chat.id, sent.message_id))

@bot.message_handler(content_types=AnyContentType())
@nonfalling_handler
def another_content_type_handler(message: telebot.types.Message):
    bot.reply_to(message, "Сообщения этого типа не поддерживаются. Свяжитесь с @kolayne, чтобы добавить поддержку")


if __name__ == "__main__":
    bot.polling(none_stop=False)
