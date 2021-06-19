from sys import stderr
from typing import Callable, Any

from .db_connector import DatabaseConnectionPool, cursor_type
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

        self.send_invitation_callback = send_invitation_callback
        self.delete_invitation_callback = delete_invitation_callback

    def _invite_operator_to_client(self, cursor: cursor_type, operator_chat_id: int, client_chat_id: int) -> None:
        client_local_id = self.users_controller.get_local_id(client_chat_id)

        sent_message_id = self.send_invitation_callback(operator_chat_id, client_chat_id,
                                                        f"Пользователь №{client_local_id} хочет побеседовать. Нажмите "
                                                        "кнопку ниже, чтобы стать его оператором")

        # Unless message sending failed for some internal front-end reason, store invitation in the database
        if sent_message_id is not None:
            try:
                # Invitation leak protection.
                # Note: if there is a conflict, the exception won't be raised, because of `ON CONFLICT DO NOTHING`.
                # We'll check if there was a problem based on `cursor.rowcount`. That's on purpose: we don't want an
                # exception to be raised here, because if it is raised, the current transaction of `cursor` (which was
                # started outside of this function and might contain some important changes already) will be aborted
                cursor.execute("INSERT INTO sent_invitations(operator_chat_id, client_chat_id, invitation_message_id) "
                               "VALUES (%s, %s, %s) "
                               "ON CONFLICT (operator_chat_id, client_chat_id) DO NOTHING",
                               (operator_chat_id, client_chat_id, sent_message_id))
                if cursor.rowcount == 0:
                    print("Warning: an invitation leak has occurred. Dropping one of the invitation messages",
                          file=stderr)
                    self.delete_invitation_callback(operator_chat_id, sent_message_id)
            except Exception:
                # However, even if an exception was raised (for any reason other than
                # `CONFLICT (operator_chat_id, client_chat_id)`, we still don't want the invitation to be leaked!
                print("An exception occurred. It will be raised back, but now need to delete the leaked invitation "
                      "first", file=stderr)
                self.delete_invitation_callback(operator_chat_id, sent_message_id)
                raise  # Raise the caught exception

    def invite_to_client(self, client_chat_id: int) -> None:
        """
        Sends out invitation messages to all currently free operators, via which they can start a conversation with the
        client

        :param client_chat_id: Messenger identifier of the user to invite operators to have conversation with
        """
        with self._conn_pool.PrettyCursor() as cursor:
            # Prevent any invitations from being sent or deleted by parallel transactions until this one completes,
            # because, for example, a parallel transaction might try to clear invitations for a user, for which we **are
            # about** to send an invitation to, but have not sent yet
            cursor.execute("LOCK TABLE sent_invitations IN SHARE MODE")

            """
            Explanation of the query below:

            This query selects chat ids of all the operators which should receive an invitation to the given client
            (i.e. they are currently not in conversations, and they haven't yet been sent an invitation to the client).
            We select them with the two joins in the following way (of course, PostgreSQL doesn't do exactly what I say
            here, it performs optimizations. But the result is exactly as if it would be if pgsql was
            doing the following):
            1. SELECT all the users, which are operators (see `WHERE users.is_operator` in the end of the query)
            2. If the client himself is an operator, he shouldn't receive a notification. Remove him from the
                resulting set (`WHERE ... AND users.chat_id != <client_chat_id>`)
            3. LEFT OUTER JOIN the selected users with `conversations` (note the `ON` clause: the rows are considered
                matching if the user is in a conversation in any role) and forget users which are in conversations
                (`WHERE ... AND conversations.operator_chat_id IS NULL`)
            4. Another unusual LEFT OUTER JOIN: we join the remaining users with `sent_invitations`, where a user row
                is considered to be matching an invitation row if the user is the operator, to which the invitation
                was sent AND the invitation client is the client we're currently processing. This way we get rid of
                other invitations sent for this operator.
                After that we only keep the operators which don't yet have an invitation sent to the client
                (`WHERE ... AND sent_invitations.client_chat_id IS NULL`)

            That's it! Now we have the list of operators which should receive an invitation to the client.
            """
            # FIXME: fuck, this query relies on tables `users`, `conversations`, and `sent_invitations`, while
            #  `InvitationsController` should only rely on `sent_invitations`. Have to do something with it. Either
            #  somehow improve the API of the three controllers, or document, that the controllers can't actually be
            #  safely replaced with other classes of the same interface
            cursor.execute("SELECT users.chat_id "
                           "FROM users "

                           "   LEFT OUTER JOIN conversations ON users.chat_id = conversations.operator_chat_id "
                           "                                    OR users.chat_id = conversations.client_chat_id "

                           "   LEFT OUTER JOIN sent_invitations ON users.chat_id = sent_invitations.operator_chat_id "
                           "                                       AND sent_invitations.client_chat_id = %s "

                           "WHERE users.is_operator "
                           "  AND users.chat_id != %s"
                           "  AND conversations.operator_chat_id IS NULL "
                           "  AND sent_invitations.client_chat_id IS NULL ",
                           (client_chat_id, client_chat_id))

            for operator_chat_id, in cursor.fetchall():
                self._invite_operator_to_client(cursor, operator_chat_id, client_chat_id)

    def invite_for_operator(self, operator_chat_id: int) -> None:
        with self._conn_pool.PrettyCursor() as cursor, \
                self.conversations_controller.get_conversations_requesters_with_plocking() as conversations_requesters:

            # Prevent any invitations from being sent or deleted by parallel transactions until this one completes,
            # because, for example, a parallel transaction might try to clear invitations for a user, for which we **are
            # about** to send an invitation to, but have not sent yet
            cursor.execute("LOCK TABLE sent_invitations IN SHARE MODE")

            for client_chat_id in conversations_requesters:
                self._invite_operator_to_client(cursor, operator_chat_id, client_chat_id)

    def clear_invitations_to_client(self, client_chat_id: int) -> bool:
        """
        Remove messages, inviting to a conversation with the client

        :param client_chat_id: Messenger identifier of the client to remove invitations to conversation with
        :return: `True` if there was at least one invitation sent earlier for this client (and, therefore, has now been
            removed), `False` otherwise
        """
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("DELETE FROM sent_invitations WHERE client_chat_id = %s "
                           "RETURNING operator_chat_id, invitation_message_id",
                           (client_chat_id,))
            for operator_chat_id, invitation_message_id in cursor.fetchall():
                self.delete_invitation_callback(operator_chat_id, invitation_message_id)
            return cursor.rowcount > 0

    def clear_invitations_for_operator(self, operator_chat_id: int) -> None:
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("DELETE FROM sent_invitations WHERE operator_chat_id = %s RETURNING invitation_message_id",
                           (operator_chat_id,))
            for invitation_message_id, in cursor.fetchall():
                self.delete_invitation_callback(operator_chat_id, invitation_message_id)
            return cursor.rowcount > 0
