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
    bot.reply_to(message, "Привет! Мои команды:\n"
                          "/request_conversation - Запросить анонимную беседу с оператором\n"
                          "/end_conversation - Прекратить беседу или отменить запрос\n\n"
                          "Обратите внимание, что во время бесед вы:\n"
                          "1. Не увидите, как ваш собеседник печатает\n"
                          "2. Не сможете редактировать или удалять сообщения")
    core.add_user_if_not_exists(message.chat.id)


@bot.message_handler(commands=['request_conversation'])
@nonfalling_handler
def request_conversation_handler(message: telebot.types.Message):
    with core.request_conversation_with_locking(message.chat.id) as res:
        if res == 0:
            bot.reply_to(message, "Операторы получили запрос на присоединение. Ждем оператора...\nИспользуйте "
                                  "/end_conversation, чтобы отменить запрос")
        elif res == 1:
            bot.reply_to(message, "Вы уже ожидаете оператора. Используйте /end_conversation, чтобы отказаться от "
                                  "беседы")
        elif res == 2:
            bot.reply_to(message, "Вы уже в беседе. Используйте /end_conversation, чтобы выйти из нее")
        else:
            raise RuntimeError("`core.request_conversation_with_locking` has returned an unexpected value")


@bot.message_handler(commands=['end_conversation'])
@nonfalling_handler
def end_conversation_handler(message: telebot.types.Message):
    with core.end_conversation_or_cancel_request_with_plocking(message.chat.id) as (client_tg_id, operator_tg_id):
        if client_tg_id is None:
            bot.reply_to(message, "В данный момент вы ни с кем не беседуете. Используйте /request_conversation, чтобы "
                                  "начать")
        elif operator_tg_id is None:
            bot.reply_to(message, "Ожидание операторов отменено. Используйте /request_conversation, чтобы запросить "
                                  "помощь снова")
        else:
            operator_local_id = core.get_local_id(operator_tg_id)
            client_local_id = core.get_local_id(client_tg_id)

            keyboard = telebot.types.InlineKeyboardMarkup()
            d = {'type': 'conversation_rate', 'operator_ids': [operator_tg_id, operator_local_id],
                 'client_local_id': client_local_id,
                 'conversation_end_moment': seconds_since_local_epoch(datetime.now())}

            keyboard.add(
                telebot.types.InlineKeyboardButton("Лучше",
                                                   callback_data=shorten_callback_data_and_jdump(
                                                       {**d, 'mood': 'better'})),
                telebot.types.InlineKeyboardButton("Так же",
                                                   callback_data=shorten_callback_data_and_jdump(
                                                       {**d, 'mood': 'same'})),
                telebot.types.InlineKeyboardButton("Хуже",
                                                   callback_data=shorten_callback_data_and_jdump(
                                                       {**d, 'mood': 'worse'}))
            )
            keyboard.add(telebot.types.InlineKeyboardButton("Не хочу оценивать",
                                                            callback_data=shorten_callback_data_and_jdump(d)))

            bot.send_message(client_tg_id, "Беседа с оператором прекращена. Хотите оценить свое самочувствие после "
                                           "нее? Вы остаетесь анонимным", reply_markup=keyboard)
            bot.send_message(operator_tg_id, f"Беседа с пользователем №{client_local_id} прекращена")


@bot.message_handler(content_types=AnyContentType())
@nonfalling_handler
def text_message_handler(message: telebot.types.Message):
    with core.get_conversing_with_plocking(message.chat.id) as (client_tg_id, operator_tg_id):
        if client_tg_id is None:
            bot.reply_to(message, "Чтобы начать общаться с оператором, нужно написать /request_conversation. Сейчас "
                                  "у вас нет собеседника")
            return

        if operator_tg_id is None:
            bot.reply_to(message, "У вас пока нет собеседника. Подождите, пока оператор присоединится к беседе. "
                                  "Используйте /end_conversation чтобы отменить ожидание оператора")
            return

        interlocutor_id = client_tg_id if message.chat.id == operator_tg_id else operator_tg_id

        reply_to = None
        if message.reply_to_message is not None:
            # TODO: god, this line (and similar one below) is so disgusting. I want to fix it ASAP. #22
            with core._users_controller._conn_pool.PrettyCursor() as cursor:
                # Note: it doesn't really matter who was the actual sender and receiver, because there were both
                # versions inserted to the database
                cursor.execute("SELECT interlocutor1_message_id FROM reflected_messages "
                               "WHERE interlocutor1_chat_id = %s AND interlocutor2_chat_id = %s AND "
                               "      interlocutor2_message_id = %s",
                               (interlocutor_id, message.chat.id, message.reply_to_message.message_id))
                try:
                    reply_to, = cursor.fetchone()
                except TypeError:
                    bot.reply_to(message, "Эта беседа уже завершилась. Вы не можете ответить на это сообщение")
                    return

        sent = bot.copy_message(interlocutor_id, message.chat.id, message.message_id, reply_to_message_id=reply_to)

        with core._users_controller._conn_pool.PrettyCursor() as cursor:
            # Storing this message in two ways: both as if it was send by the client and by the operator. This way, we
            # won't need to check, which way it actually was, when later processing a reply to a message (user can reply
            # both to his own message and to his interlocutor's one)
            query = "INSERT INTO reflected_messages(interlocutor1_chat_id, interlocutor1_message_id, " \
                    "interlocutor2_chat_id, interlocutor2_message_id) " \
                    "VALUES (%s, %s, %s, %s)"
            cursor.execute(query, (message.chat.id, message.message_id, interlocutor_id, sent.message_id))
            cursor.execute(query, (interlocutor_id, sent.message_id, message.chat.id, message.message_id))
