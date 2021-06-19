import telebot

from ._init_objects import bot, core
from .utils.tg_callback_shortener import jload_and_expand_callback_data, datetime_from_local_epoch_secs
from .utils.common import nonfalling_handler, notify_admins


def get_type_from_callback_data(call_data):
    d = jload_and_expand_callback_data(call_data)
    if not isinstance(d, dict):
        return None
    return d.get('type')


# Invalid callback query handler
@bot.callback_query_handler(func=lambda call: get_type_from_callback_data(call.data) is None)
@nonfalling_handler
def invalid_callback_query(call: telebot.types.CallbackQuery):
    bot.answer_callback_query(call.id, "Действие не поддерживается или некорректные данные обратного вызова")


@bot.callback_query_handler(func=lambda call: get_type_from_callback_data(call.data) == 'conversation_rate')
@nonfalling_handler
def conversation_rate_callback_query(call: telebot.types.CallbackQuery):
    d = jload_and_expand_callback_data(call.data)

    mood = d.get('mood')
    if mood == 'worse':
        operator_tg, operator_local = d['operator_ids']
        client_local = d['client_local_id']
        conversation_end_moment = datetime_from_local_epoch_secs(d['conversation_end_moment'])

        notification_text = f"Клиент {client_local} чувствует себя хуже после беседы с оператором " \
                            f"[{operator_local}](tg://user?id={operator_tg}), которая завершилась в " \
                            f"{conversation_end_moment}"
        notify_admins(text=notification_text, parse_mode="Markdown")

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    if mood is None:
        bot.answer_callback_query(call.id)
    else:
        bot.answer_callback_query(call.id, "Спасибо за вашу оценку")


@bot.callback_query_handler(func=lambda call: get_type_from_callback_data(call.data) == 'conversation_acceptation')
@nonfalling_handler
def conversation_acceptation_callback_query(call: telebot.types.CallbackQuery):
    d = jload_and_expand_callback_data(call.data)

    with core.begin_conversation_with_locking(d['client_id'], call.message.chat.id) as result:
        if result == 0:
            local_client_id = core.get_local_id(d['client_id'])
            local_operator_id = core.get_local_id(call.message.chat.id)
            bot.send_message(call.message.chat.id, f"Началась беседа с клиентом №{local_client_id}. Отправьте "
                                                   "сообщение, и собеседник его увидит")
            bot.send_message(d['client_id'], f"Началась беседа с оператором №{local_operator_id}. Отправьте сообщение, "
                                             "и собеседник его увидит")
            bot.answer_callback_query(call.id)
        elif result == 1:
            notify_admins(text="Consistency error: someone is trying to accept an invitation, where a client is "
                               "operating!\nBut probably the client just has very quick fingers...")
            bot.answer_callback_query(call.id, "Похоже, это приглашение устарело. Попробуйте еще раз")
        elif result == 2:
            bot.answer_callback_query(call.id, "Невозможно начать беседу, пока вы ожидаете оператора")
        elif result == 3 or result == 4:
            notify_admins(text="Consistency error: someone is trying to accept an invitation while being in a "
                               "conversation already!")
            bot.answer_callback_query(call.id, "Вы не можете принять приглашение, пока сами находитесь в беседе")
        elif result == 5:
            bot.answer_callback_query(call.id, "Похоже, это приглашение уже принял другой оператор")
        else:
            raise RuntimeError("`core.begin_conversation` returned an unexpected error code")
