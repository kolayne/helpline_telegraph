from sys import stderr
from traceback import format_exc

import telebot
from typing import Callable, Any

from .users import UsersController
from .conversations import ConversationsController


class InvitationsController:
    def __init__(self, users_controller: UsersController, conversations_controller: ConversationsController,
                 send_invitation_callback: Callable[[int, int, str], int],
                 delete_invitation_callback: Callable[[int, int], Any]):
        self.users_controller = users_controller
        self.conversations_controller = conversations_controller

        # Whenever a client requests a conversation, all the <b>free</b> operators get a message which invites them to
        # start chatting with that client. Whenever an operator accepts the invitation, all the messages which invite to
        # the conversation with that client are deleted, and the conversation begins between the client and the operator
        # who accepted the invitation

        # `_operators_invitations_messages` is used for storing sent invitations messages for being able to delete them
        # later. It is a dictionary from telegram client id to a list of tuples of telegram operator chat id and
        # telegram id of a message, which invites the operator to join a conversation with the client
        # (simpler `{client_id: [(operator_id, message_id)]}`)
        self._operators_invitations_messages = {}

        self.send_invitation_callback = send_invitation_callback
        self.delete_invitation_callback = delete_invitation_callback

    def invite_operators(self, tg_client_id: int) -> int:
        """
        Sends out invitation messages to all currently free operators, via which they can start a conversation with the
        client

        :param tg_client_id: Telegram identifier of the user to invite operators to chat with
        :return: Error code, either of `0`, `1`, `2`, `3`, where `0` indicates that the invitations have been sent
            successfully, `1` tells that the user had requested invitations before, `2` indicates that there are no free
            operators, `3` means that the client is in a conversation already (either as a client or as an operator)
        """
        local_client_id = self.users_controller.get_local_id(tg_client_id)

        with self.conversations_controller.conversations_starter_finisher_lock:
            free_operators = set(self.users_controller.get_free_operators()) - {tg_client_id}
            if not free_operators:
                return 2

            if tg_client_id in self._operators_invitations_messages.keys():
                return 1

            # In a conversation already
            if self.conversations_controller.get_conversing(tg_client_id) != ((None, None), (None, None)):
                return 3

            msg_ids = []
            for tg_operator_id in free_operators:
                try:
                    msg_ids.append((
                        tg_operator_id,
                        self.send_invitation_callback(tg_operator_id, tg_client_id,
                                                      f"Пользователь №{local_client_id} хочет побеседовать. Нажмите "
                                                      "кнопку ниже, чтобы стать его оператором")
                    ))
                except telebot.apihelper.ApiException:
                    print("Telegram API Exception while sending out operators invitations:", file=stderr)
                    print(format_exc(), file=stderr)

            self._operators_invitations_messages[tg_client_id] = msg_ids

        return 0

    def clear_invitation_messages(self, tg_client_id: int) -> bool:
        """
        Remove messages with invitations to a conversation with the client sent to operators

        :param tg_client_id: Telegram identifier of the client to remove invitations to conversation with
        :return: `True` if there was at least one invitation sent earlier for this client (and, therefore, had now been
            removed), `False` otherwise
        """
        with self.conversations_controller.conversations_starter_finisher_lock:
            if tg_client_id in self._operators_invitations_messages.keys():
                for (operator_id, message_id) in self._operators_invitations_messages[tg_client_id]:
                    self.delete_invitation_callback(operator_id, message_id)
                del self._operators_invitations_messages[tg_client_id]

                return True
            else:
                return False
