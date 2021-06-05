from datetime import datetime

import telebot

from ._init_objects import bot, core
from .utils.common import nonfalling_handler
from .utils.tg_callback_shortener import seconds_since_local_epoch, shorten_callback_data_and_jdump


class AnyContentType:
    def __contains__(self, item): return True


@bot.message_handler(commands=['start', 'help'])
@nonfalling_handler
def start_help_handler(message: telebot.types.Message):
    bot.reply_to(message, "Привет. /request_conversation, чтобы начать беседу, /end_conversation чтобы завершить")
    core.add_user(message.chat.id)


@bot.message_handler(commands=['request_conversation'])
@nonfalling_handler
def request_conversation_handler(message: telebot.types.Message):
    (tg_client_id, _), (tg_operator_id, _) = core.get_conversing(message.chat.id)
    if tg_operator_id == message.chat.id:
        bot.reply_to(message, "Операторы не могут запрашивать помощь, пока помогают кому-то")
    elif tg_client_id == message.chat.id:
        bot.reply_to(message, "Вы уже в беседе с оператором. Используйте /end_conversation чтобы прекратить")
    else:
        result = core.invite_operators(message.chat.id)
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
    (_, client_local), (operator_tg, operator_local) = core.get_conversing(message.chat.id)

    if operator_tg is None:
        if core.clear_invitation_messages(message.chat.id):
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
             'client_local_id': client_local, 'conversation_end_moment': seconds_since_local_epoch(datetime.now())}

        keyboard.add(
            telebot.types.InlineKeyboardButton("Лучше",
                                               callback_data=shorten_callback_data_and_jdump({**d, 'mood': 'better'})),
            telebot.types.InlineKeyboardButton("Так же",
                                               callback_data=shorten_callback_data_and_jdump({**d, 'mood': 'same'})),
            telebot.types.InlineKeyboardButton("Хуже",
                                               callback_data=shorten_callback_data_and_jdump({**d, 'mood': 'worse'}))
        )
        keyboard.add(telebot.types.InlineKeyboardButton("Не хочу оценивать",
                                                        callback_data=shorten_callback_data_and_jdump(d)))

        core.end_conversation(message.chat.id)
        bot.reply_to(message, "Беседа с оператором прекратилась. Хотите оценить свое самочувствие после нее? "
                              "Вы остаетесь анонимным", reply_markup=keyboard)
        bot.send_message(operator_tg, f"Пользователь №{client_local} прекратил беседу")


@bot.message_handler(content_types=['text'])
@nonfalling_handler
def text_message_handler(message: telebot.types.Message):
    (client_tg, _), (operator_tg, _) = core.get_conversing(message.chat.id)

    if client_tg is None:
        bot.reply_to(message, "Чтобы начать общаться с оператором, нужно написать /request_conversation. Сейчас у вас "
                              "нет собеседника")
        return

    interlocutor_id = client_tg if message.chat.id == operator_tg else operator_tg

    reply_to = None
    if message.reply_to_message is not None:
        # TODO: god, this line (and similar one below) is so disgusting. I want to fix it ASAP. #22
        with core._users_controller._conn_pool.PrettyCursor() as cursor:
            # Note: it doesn't really matter who was the actual sender and receiver, because there were both versions
            # inserted to the database
            cursor.execute("SELECT sender_message_id FROM reflected_messages WHERE sender_chat_id=%s AND "
                           "receiver_chat_id=%s AND receiver_message_id=%s",
                           (interlocutor_id, message.chat.id, message.reply_to_message.message_id))
            try:
                reply_to, = cursor.fetchone()
            except TypeError:
                bot.reply_to(message, "Эта беседа уже завершилась. Вы не можете ответить на это сообщение")
                return

    for entity in message.entities or []:
        if entity.type in ('mention', 'bot_command'):
            continue
        if entity.type == 'url' and message.text[entity.offset: entity.offset + entity.length] == entity.url:
            continue

        bot.reply_to(message, "Это сообщение содержит форматирование, которое сейчас не поддерживается. Оно будет "
                              "отправлено с потерей форматирования. Мы работаем над этим")
        break

    sent = bot.send_message(interlocutor_id, message.text, reply_to_message_id=reply_to)

    with core._users_controller._conn_pool.PrettyCursor() as cursor:
        # Storing this message in two ways: both as if it was send by the client and by the operator. This way, we won't
        # need to check, which way it actually was, when later processing a reply to a message (user can reply both to
        # his own message and to his interlocutor's one)
        query = "INSERT INTO reflected_messages(sender_chat_id, sender_message_id, receiver_chat_id, " \
                "receiver_message_id) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (message.chat.id, message.message_id, sent.chat.id, sent.message_id))
        cursor.execute(query, (sent.chat.id, sent.message_id, message.chat.id, message.message_id))


@bot.message_handler(content_types=AnyContentType())
@nonfalling_handler
def another_content_type_handler(message: telebot.types.Message):
    bot.reply_to(message, "Сообщения этого типа не поддерживаются. Свяжитесь с @kolayne, чтобы добавить поддержку")
