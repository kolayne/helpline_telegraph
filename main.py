import json
from datetime import datetime
from functools import wraps
from sys import stderr
from traceback import format_exc
from threading import Lock

import telebot
from typing import Callable

from common import does_raise
from db_connector import PrettyCursor
from logic import add_user, begin_conversation, end_conversation, get_conversing, get_admins_ids, get_free_operators, \
    get_local
from config import bot_token
from callback_helpers import contract_callback_data_and_jdump, jload_and_decontract_callback_data, \
    seconds_since_local_epoch, datetime_from_local_epoch_secs


bot = telebot.TeleBot(bot_token)


# Whenever a client wants to have a conversation all the free operators get a message which invites him to the
# conversation with the client. Whenever an operator accepts the invitation, all the invitations messages for other
# operators are deleted.

# `operators_invitations_messages` is used for storing sent invitations messages for being able to delete them later. It
# is a dictionary from telegram client id to a list of tuples of telegram operator chat id and telegram id of a message,
# which invites the operator to join a conversation with the client (simpler `{client_id: [(operator_id, message_id)]}`)
operators_invitations_messages = {}
# `conversation_request_lock` is a lock which must be acquired when working with `operators_invitations_messages`
conversation_starter_lock = Lock()


def invite_operators(tg_client_id: int) -> int:
    """
    Sends out invitation messages to all currently free operators, via which they can start a conversation with the
    client

    :param tg_client_id: Telegram identifier of the user to invite operators to chat with
    :return: Error code, either of `0`, `1`, `2`, `3`, where `0` indicates that the invitations have been sent
        successfully, `1` tells the user had requested invitations before, `2` indicates that there are no free
        operators, `3` means that the client is in a conversation already (either as a client or as an operator)
    """
    if get_conversing(tg_client_id) != ((None, None), (None, None)):  # In a conversation already
        return 3

    free_operators = set(get_free_operators()) - {tg_client_id}
    if not free_operators:
        return 2

    keyboard = telebot.types.InlineKeyboardMarkup()
    callback_data = {'type': 'conversation_acceptation', 'client_id': tg_client_id}
    keyboard.add(telebot.types.InlineKeyboardButton("Присоединиться",
                                                    callback_data=contract_callback_data_and_jdump(callback_data)))
    local_client_id = get_local(tg_client_id)

    with conversation_starter_lock:
        if tg_client_id in operators_invitations_messages.keys():
            return 1

        msg_ids = []
        for tg_operator_id in free_operators:
            try:
                msg_ids.append((
                    tg_operator_id,
                    bot.send_message(tg_operator_id, f"Пользователь №{local_client_id} хочет побеседовать. Нажмите "
                                                     "кнопку ниже, чтобы стать его оператором",
                                     reply_markup=keyboard).message_id
                ))
            except telebot.apihelper.ApiException:
                print("Telegram API Exception while sending out operators invitations:", file=stderr)
                print(format_exc(), file=stderr)

        operators_invitations_messages[tg_client_id] = msg_ids

    return 0


def clear_invitation_messages(tg_client_id: int) -> bool:
    """
    Remove invitation messages sent to operators for the client

    :param tg_client_id: Telegram identifier of the client to remove invitations to conversation with
    :return: `True` if there was at least one invitation sent earlier for this client (and, therefore, had now been
        removed), `False` otherwise
    """
    with conversation_starter_lock:
        if tg_client_id in operators_invitations_messages.keys():
            for (operator_id, message_id) in operators_invitations_messages[tg_client_id]:
                bot.delete_message(operator_id, message_id)
            del operators_invitations_messages[tg_client_id]

            return True
        else:
            return False


def notify_admins(**kwargs) -> bool:
    """
    Send a text message to all the bot administrators. Any exceptions occurring inside are suppressed

    ::param kwargs: Keyword arguments to be forwarded to `bot.send_message` (shouldn't contain `chat_id`)
    :return: `True` if a message was successfully delivered to at least one admin (i. e. no exception occurred), `False`
        otherwise
    """
    try:
        admins = get_admins_ids()
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


def nonfalling_handler(func: Callable):
    @wraps(func)
    def ans(message: telebot.types.Message, *args, **kwargs):
        try:
            func(message, *args, **kwargs)
        except Exception:
            try:
                # For callback query handlers (we got a `telebot.types.CallbackQuery` object instead of a message)
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
                print(format_exc(), file=stderr)

    return ans


class AnyContentType:
    def __contains__(self, item): return True


@bot.message_handler(commands=['start', 'help'])
@nonfalling_handler
def start_help_handler(message: telebot.types.Message):
    bot.reply_to(message, "Привет. /request_conversation, чтобы начать беседу, /end_conversation чтобы завершить")
    add_user(message.chat.id)

@bot.message_handler(commands=['request_conversation'])
@nonfalling_handler
def request_conversation_handler(message: telebot.types.Message):
    (tg_client_id, _), (tg_operator_id, _) = get_conversing(message.chat.id)
    if tg_operator_id == message.chat.id:
        bot.reply_to(message, "Операторы не могут запрашивать помощь, пока помогают кому-то\nОбратитесь к @kolayne "
                              "для реализации такой возможности")
    elif tg_client_id == message.chat.id:
        bot.reply_to(message, "Вы уже в беседе с оператором. Используйте /end_conversation чтобы прекратить")
    else:
        result = invite_operators(message.chat.id)
        if result == 0:
            bot.reply_to(message, "Операторы получили запрос на присоединение. Ждем оператора...\nИспользуйте "
                                  "/end_conversation, чтобы отменить запрос")
        elif result == 1:
            bot.reply_to(message, "Вы уже ожидаете присоединения оператора. Используйте /end_conversation, чтобы "
                                  "отказаться от беседы")
        elif result == 2:
            bot.reply_to(message, "Сейчас нет свободных операторов. Пожалуйста, попробуйте позже")
        elif result == 3:
            bot.reply_to(message, "Вы уже в беседе. Используйте /end_conversation, чтобы выйти из нее")
        else:
            raise NotImplementedError("`invite_operators` returned an unexpected value")


@bot.message_handler(commands=['end_conversation'])
@nonfalling_handler
def end_conversation_handler(message: telebot.types.Message):
    (_, client_local), (operator_tg, operator_local) = get_conversing(message.chat.id)

    if operator_tg is None:
        if clear_invitation_messages(message.chat.id):
            bot.reply_to(message, "Ожидание операторов отменено. Используйте /request_conversation, чтобы запросить "
                                  "помощь снова")
        else:
            bot.reply_to(message, "В данный момент вы ни с кем не беседуете. Используйте /request_conversation, чтобы "
                                  "начать")
    elif operator_tg == message.chat.id:
        bot.reply_to(message, "Оператор не может прекратить беседу. Обратитесь к @kolayne для реализации такой "
                              "возможности")
    else:
        keyboard = telebot.types.InlineKeyboardMarkup()
        d = {'type': 'conversation_rate', 'operator_ids': [operator_tg, operator_local],
             'conversation_end_moment': seconds_since_local_epoch(datetime.now())}

        keyboard.add(
            telebot.types.InlineKeyboardButton("Лучше",
                                               callback_data=contract_callback_data_and_jdump({**d, 'mood': 'better'})),
            telebot.types.InlineKeyboardButton("Так же",
                                               callback_data=contract_callback_data_and_jdump({**d, 'mood': 'same'})),
            telebot.types.InlineKeyboardButton("Хуже",
                                               callback_data=contract_callback_data_and_jdump({**d, 'mood': 'worse'}))
        )
        keyboard.add(telebot.types.InlineKeyboardButton("Не хочу оценивать",
                                                        callback_data=contract_callback_data_and_jdump(d)))

        end_conversation(message.chat.id)
        bot.reply_to(message, "Беседа с оператором прекратилась. Хотите оценить свое самочувствие после нее? "
                              "Вы остаетесь анонимным", reply_markup=keyboard)
        bot.send_message(operator_tg, f"Пользователь №{client_local} прекратил беседу")

@bot.message_handler(content_types=['text'])
@nonfalling_handler
def text_message_handler(message: telebot.types.Message):
    (client_tg, _), (operator_tg, _) = get_conversing(message.chat.id)

    if client_tg is None:
        bot.reply_to(message, "Чтобы начать общаться с оператором, нужно написать /request_conversation. Сейчас у вас "
                              "нет собеседника")
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


# Invalid callback query handler
@bot.callback_query_handler(func=lambda call: does_raise(json.loads, args=(call.data,), expected=json.JSONDecodeError,
                                                         reraise_other=False) or
                                              'type' not in jload_and_decontract_callback_data(call.data).keys())
@nonfalling_handler
def invalid_callback_query(call: telebot.types.CallbackQuery):
    bot.answer_callback_query(call.id, "Действие не поддерживается или некорректные данные обратного вызова")


@bot.callback_query_handler(func=lambda call: jload_and_decontract_callback_data(call.data)['type'] ==
                                              'conversation_rate')
@nonfalling_handler
def conversation_rate_callback_query(call: telebot.types.CallbackQuery):
    d = jload_and_decontract_callback_data(call.data)

    mood = d.get('mood')
    if mood == 'worse':
        operator_tg, operator_local = d['operator_ids']
        conversation_end = datetime_from_local_epoch_secs(d['conversation_end_moment'])
        notification_text = "Клиент чувствует себя хуже после беседы с оператором {}, которая завершилась в {}".format(
            f"[{operator_local}](tg://user?id={operator_tg})", conversation_end
        )
        notify_admins(text=notification_text, parse_mode="Markdown")

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    if mood is None:
        bot.answer_callback_query(call.id)
    else:
        bot.answer_callback_query(call.id, "Спасибо за вашу оценку")


@bot.callback_query_handler(func=lambda call: jload_and_decontract_callback_data(call.data)['type'] ==
                                              'conversation_acceptation')
@nonfalling_handler
def conversation_acceptation_callback_query(call: telebot.types.CallbackQuery):
    d = jload_and_decontract_callback_data(call.data)
    with conversation_starter_lock:
        if call.message.chat.id in operators_invitations_messages.keys():
            bot.answer_callback_query(call.id, "Невозможно начать беседу, пока вы ожидаете оператора")
            return

        conversation_began = begin_conversation(d['client_id'], call.message.chat.id)

    if conversation_began:
        clear_invitation_messages(d['client_id'])

        (_, local_client_id), (_, local_operator_id) = get_conversing(call.message.chat.id)
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"Началась беседа с клиентом №{local_client_id}. Отправьте "
                                               "сообщение, и собеседник его увидит")
        bot.send_message(d['client_id'], f"Началась беседа с оператором №{local_operator_id}. Отправьте сообщение, "
                                         "и собеседник его увидит")
    else:
        bot.answer_callback_query(call.id, "Что-то пошло не так. Возможно, вы уже в беседе, или другой оператор принял "
                                           "это приглашение")


if __name__ == "__main__":
    bot.polling(none_stop=False)
