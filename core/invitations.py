from sys import stderr
from threading import Lock
from traceback import format_exc

import telebot

from .users import get_local_id, get_free_operators
from .conversations import get_conversing
from telegram_bot.callback_helpers import contract_callback_data_and_jdump
from telegram_bot.__main__ import bot  # TODO: remove this terrible shit


# Whenever a client requests a conversation, all the <b>free</b> operators get a message which invites them to start
# chatting with that client. Whenever an operator accepts the invitation, all the messages which invite to the
# conversation with that client are deleted, and the conversation begins between the client and the operator who
# accepted the invitation

# `operators_invitations_messages` is used for storing sent invitations messages for being able to delete them later. It
# is a dictionary from telegram client id to a list of tuples of telegram operator chat id and telegram id of a message,
# which invites the operator to join a conversation with the client (simpler `{client_id: [(operator_id, message_id)]}`)
operators_invitations_messages = {}
# `conversation_starter_lock` is a lock which must be acquired when working with `operators_invitations_messages`
conversation_starter_lock = Lock()


def invite_operators(tg_client_id: int) -> int:
    """
    Sends out invitation messages to all currently free operators, via which they can start a conversation with the
    client

    :param tg_client_id: Telegram identifier of the user to invite operators to chat with
    :return: Error code, either of `0`, `1`, `2`, `3`, where `0` indicates that the invitations have been sent
        successfully, `1` tells that the user had requested invitations before, `2` indicates that there are no free
        operators, `3` means that the client is in a conversation already (either as a client or as an operator)
    """
    keyboard = telebot.types.InlineKeyboardMarkup()
    callback_data = {'type': 'conversation_acceptation', 'client_id': tg_client_id}
    keyboard.add(telebot.types.InlineKeyboardButton("Присоединиться",
                                                    callback_data=contract_callback_data_and_jdump(callback_data)))
    local_client_id = get_local_id(tg_client_id)

    with conversation_starter_lock:
        free_operators = set(get_free_operators()) - {tg_client_id}
        if not free_operators:
            return 2

        if tg_client_id in operators_invitations_messages.keys():
            return 1

        if get_conversing(tg_client_id) != ((None, None), (None, None)):  # In a conversation already
            return 3

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
    Remove messages with invitations to a conversation with the client sent to operators

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
