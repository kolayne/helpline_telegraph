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


@bot.callback_query_handler(func=lambda call: get_type_from_callback_data(call.data) == 'conversation_acceptation')
@nonfalling_handler
def conversation_acceptation_callback_query(call: telebot.types.CallbackQuery):
    d = jload_and_expand_callback_data(call.data)
    # TODO: There are a private member access (`core._operators_invitations_messages`) and a race condition
    #  (conversation can begin after the if statement) here. Both will be fixed with #37
    if call.message.chat.id in core._operators_invitations_messages.keys():
        bot.answer_callback_query(call.id, "Невозможно начать беседу, пока вы ожидаете оператора")
        return

    conversation_began = core.begin_conversation(d['client_id'], call.message.chat.id)

    if conversation_began:
        core.clear_invitation_messages(d['client_id'])

        (_, local_client_id), (_, local_operator_id) = core.get_conversing(call.message.chat.id)
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"Началась беседа с клиентом №{local_client_id}. Отправьте "
                                               "сообщение, и собеседник его увидит")
        bot.send_message(d['client_id'], f"Началась беседа с оператором №{local_operator_id}. Отправьте сообщение, "
                                         "и собеседник его увидит")
    else:
        bot.answer_callback_query(call.id, "Что-то пошло не так. Возможно, вы уже в беседе, или другой оператор принял "
                                           "это приглашение")
