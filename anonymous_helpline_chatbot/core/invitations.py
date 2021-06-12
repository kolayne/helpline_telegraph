from typing import Callable, Any

from .db_connector import DatabaseConnectionPool
from .users import UsersController
from .conversations import ConversationsController


class InvitationsController:
    def __init__(self, database_connection_pool: DatabaseConnectionPool,
                 users_controller: UsersController, conversations_controller: ConversationsController,
                 send_invitation_callback: Callable[[int, int, str], int],
                 delete_invitation_callback: Callable[[int, int], Any]):
        self._conn_pool = database_connection_pool

        self.users_controller = users_controller
        self.conversations_controller = conversations_controller

        # Whenever a client requests a conversation, all the <b>free</b> operators get a message which invites them to
        # start chatting with that client. Whenever an operator accepts the invitation, all the messages which invite to
        # the conversation with that client are deleted, and the conversation begins between the client and the operator
        # who accepted the invitation.
        # However, the above behavior will be altered soon

        self.send_invitation_callback = send_invitation_callback
        self.delete_invitation_callback = delete_invitation_callback

    def invite_operators(self, client_chat_id: int) -> int:
        """
        Sends out invitation messages to all currently free operators, via which they can start a conversation with the
        client

        :param client_chat_id: Messenger identifier of the user to invite operators to have conversation with
        :return: Error code, either of `0`, `1`, `2`, `3`, where `0` indicates that the invitations have been sent
            successfully, `2` means that either the user had requested invitations before, or there are no free
            operators, `3` means that the client is in a conversation already (either as a client or as an operator)
        """
        client_local_id = self.users_controller.get_local_id(client_chat_id)

        with self._conn_pool.PrettyCursor() as cursor:
            # Warning: it is assumed that no users can become operators or stop being operators while the chat bot is
            #   running. Otherwise also need to do something with the `users` table
            # Prevent any data modifications in tables `conversations` or `sent_invitations`. This is to avoid
            #   new conversations starting or invitations being sent (or removed!) by parallel transactions,
            #   until this one completes
            cursor.execute("LOCK TABLE conversations, sent_invitations IN SHARE MODE")

            cursor.execute("SELECT EXISTS(SELECT 1 FROM conversations "
                           "              WHERE client_chat_id = %s OR operator_chat_id = %s)",
                           (client_chat_id, client_chat_id))
            # In a conversation already (either as a client or as an operator)
            if cursor.fetchone()[0]:
                return 3

            """
            Explanation of the query below:
            
            This query selects chat ids of all the operators which should receive an invitation to the given client
            (i.e. they are currently not in conversations, and they haven't yet been sent an invitation to the client).
            We select them with the two joins in the following way (of course, PostgreSQL doesn't do exactly what I say
            here, it performs optimizations. But the result is exactly as if it was doing the following):
            1. SELECT all the users, which are operators (see `WHERE users.is_operator` in the end of the query)
            2. If the client himself is an operator, he shouldn't receive a notification. Remove him from the
                resulting set (`WHERE ... AND users.chat_id != <client_chat_id>`)
            3. LEFT OUTER JOIN the selected users with conversations and forget users which are in conversations
                (`WHERE ... AND conversations.operator_chat_id IS NULL`)
            4. An unusual LEFT OUTER JOIN: we join the remaining users with `sent_invitations`, but the join is on an
                interesting condition: the user row matches an invitation row if the user is the invitation operator AND
                the invitation client is the client we're currently processing. This way we get rid of other invitations
                sent for this operator.
                After that we only keep the operators which don't yet have an invitation sent to the client
                (`WHERE ... AND sent_invitations.client_chat_id IS NULL`)
            
            That's it! Now we have the list of operators which should receive an invitation to the client.
            """
            cursor.execute("SELECT users.chat_id "
                           "FROM users "
                           "   LEFT OUTER JOIN conversations ON users.chat_id = conversations.operator_chat_id "
                           "   LEFT OUTER JOIN sent_invitations ON users.chat_id = sent_invitations.operator_chat_id "
                           "                                       AND sent_invitations.client_chat_id = %s "
                           "WHERE users.is_operator "
                           "  AND users.chat_id != %s"
                           "  AND conversations.operator_chat_id IS NULL "
                           "  AND sent_invitations.client_chat_id IS NULL ",
                           (client_chat_id, client_chat_id))

            # FIXME: deprecated. The behavior below will be altered very soon
            # If no operators were found OR every operator already has an invitation
            # We actually can't distinguish between this two cases. Fortunately, we won't need to, soon
            if cursor.rowcount == 0:
                return 2

            # Each element of `sent_invitations_id_pairs` is `(operator_chat_id, sent_message_id)`
            sent_invitations_id_pairs = []
            for operator_chat_id, in cursor.fetchall():
                sent_invitations_id_pairs.append((
                    operator_chat_id,
                    self.send_invitation_callback(operator_chat_id, client_chat_id,
                                                  f"Пользователь №{client_local_id} хочет побеседовать. Нажмите "
                                                  "кнопку ниже, чтобы стать его оператором")
                ))

            for operator_chat_id, sent_message_id in sent_invitations_id_pairs:
                if sent_message_id is None:  # Couldn't send message for some front-end internal reason
                    continue

                cursor.execute("INSERT INTO sent_invitations(operator_chat_id, client_chat_id, invitation_message_id) "
                               "VALUES (%s, %s, %s)",
                               (operator_chat_id, client_chat_id, sent_message_id))

        return 0

    def clear_invitation_messages(self, client_chat_id: int) -> bool:
        """
        Remove messages with invitations to a conversation with the client sent to operators

        :param client_chat_id: Messenger identifier of the client to remove invitations to conversation with
        :return: `True` if there was at least one invitation sent earlier for this client (and, therefore, had now been
            removed), `False` otherwise
        """
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("DELETE FROM sent_invitations WHERE client_chat_id = %s "
                           "       RETURNING operator_chat_id, invitation_message_id",
                           (client_chat_id,))
            for operator_chat_id, invitation_message_id in cursor.fetchall():
                self.delete_invitation_callback(operator_chat_id, invitation_message_id)
            return cursor.rowcount > 0
