from functools import wraps
from sys import stderr
from traceback import format_exc

import telebot
from typing import Callable

from db_connector import PrettyCursor
from logic import add_user, start_conversation, end_conversation, is_operator_and_is_not_crying, get_conversing
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
    start_conversation(message.chat.id)
    (_, client_local), (operator_tg, _) = get_conversing(message.chat.id)

    # TODO: fix messages
    if operator_tg == -1:
        bot.reply_to(message, "Вы уже в беседе с оператором. Используйте /end_conversation чтобы прекратить")
    elif operator_tg == -2:
        bot.reply_to(message, "Операторы не могут запрашивать помощь, пока помогают кому-то\nОбратитесь к @kolayne для "
                              "реализации такой возможности")
    elif operator_tg == -3:
        bot.reply_to(message, "Сейчас нет доступных операторов :(\nПопробуйте позже")
    else:
        bot.reply_to(message, "Началась беседа с оператором. Отправьте сообщение, и оператор его увидит. "
                              "Используйте /end_conversation чтобы прекратить")
        bot.send_message(operator_tg, f"Пользователь №{client_local} начал беседу с вами")

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
    (client_tg, _), (operator_tg, _) = get_conversing(message.chat.id)

    if client_tg is None:
        bot.reply_to(message, "Чтобы начать общаться с оператором, нужно написать /start_conversation. Сейчас у вас "
                              "собеседника")
        return

    interlocutor_id = client_tg if message.chat.id != client_tg else operator_tg

    reply_to = None
    if message.reply_to_message is not None:
        with PrettyCursor() as cursor:
            cursor.execute("SELECT sender_message_id FROM reflected_messages WHERE sender_chat_id=%s AND "
                           "receiver_chat_id=%s AND receiver_message_id=%s",
                           (interlocutor_id, message.chat.id, message.reply_to_message.message_id))
            try:
                reply_to, = cursor.fetchone()
            except TypeError:
                bot.reply_to(message, "Эта беседа уже завершилась. Вы не можете ответить на это сообщение")
                return

    for entity in message.entities or []:
        if entity.type == 'mention':
            continue
        if entity.type == 'url' and message.text[entity.offset: entity.offset + entity.length] == entity.url:
            continue

        bot.reply_to(message, "Это сообщение содержит форматирование, которое сейчас не поддерживается. Оно будет "
                              "отправлено с потерей форматирования. Мы работаем над этим")
        break

    sent = bot.send_message(interlocutor_id, message.text, reply_to_message_id=reply_to)

    with PrettyCursor() as cursor:
        query = "INSERT INTO reflected_messages(sender_chat_id, sender_message_id, receiver_chat_id, " \
                "receiver_message_id) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (message.chat.id, message.message_id, sent.chat.id, sent.message_id))
        cursor.execute(query, (sent.chat.id, sent.message_id, message.chat.id, message.message_id))


@bot.message_handler(content_types=AnyContentType())
@nonfalling_handler
def another_content_type_handler(message: telebot.types.Message):
    bot.reply_to(message, "Сообщения этого типа не поддерживаются. Свяжитесь с @kolayne, чтобы добавить поддержку")


if __name__ == "__main__":
    bot.polling(none_stop=False)
