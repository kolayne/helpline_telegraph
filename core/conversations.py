from typing import Union, Tuple

import psycopg2.errors

from .db_connector import DatabaseConnectionPool


class ConversationsController:
    def __init__(self, database_connection_pool: DatabaseConnectionPool):
        self._conn_pool = database_connection_pool

    def get_conversing(self, tg_id: int) -> Union[Tuple[Tuple[int, int], Tuple[int, int]],
                                                  Tuple[Tuple[None, None], Tuple[None, None]]]:
        """
        Get client and operator from a conversation with the given identifier

        Retrieves both telegram and local identifiers of both client and operator of the conversation, in which the
        given user takes part. This function can be used for understanding whether current user is a client or an
        operator in his conversation, getting information about his interlocutor, etc

        :param tg_id: Telegram identifier of either a client or an operator
        :return: If there given user is not in conversation, `((None, None), (None, None))` is returned. Otherwise a
            tuple of two tuples is returned, where the first tuple describes the client, the second tuple describes the
            operator, and each of them consists of two `int`s, the first of which is the telegram id of a person, the
            second is the local id
        """
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("SELECT client_id,   (SELECT local_id FROM users WHERE tg_id=client_id), "
                           "       operator_id, (SELECT local_id FROM users WHERE tg_id=operator_id) "
                           "FROM conversations WHERE client_id=%s OR operator_id=%s",
                           (tg_id, tg_id))
            try:
                a, b, c, d = cursor.fetchone()
            except TypeError:
                return (None, None), (None, None)
            return (a, b), (c, d)

    def begin_conversation(self, tg_client_id: int, tg_operator_id: int) -> bool:
        """
        Begins a conversation between a client and an operator

        :param tg_client_id: Telegram id of the client to start conversation with
        :param tg_operator_id: Telegram id of the operator to start conversation with
        :return: `True` if the conversation was started successfully, `False` otherwise (<b>for example</b>, if either
            the client or the operator is busy). Formally, `False` is returned if the `psycopg2.errors.IntegrityError`
            exception was raised, `True` if there were no exceptions (which means, `False` will be returned if there is
            <b>anything</b> wrong with the request, e. g. the user with the `tg_operator_id` identifier is not an
            operator)
        """
        with self._conn_pool.PrettyCursor() as cursor:
            try:
                cursor.execute("INSERT INTO conversations(client_id, operator_id) VALUES (%s, %s)",
                               (tg_client_id, tg_operator_id))
            except psycopg2.errors.IntegrityError:  # Either this operator or this client is busy, or something else bad
                return False
            else:
                return True

    def end_conversation(self, tg_client_id: int) -> None:
        """
        End the conversation between the client and an operator if there is any

        Note that this function can only be called with a client id. Operator is unable to end a conversation in current
        implementation.

        :param tg_client_id: Telegram id of the client ending the conversation
        """
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("DELETE FROM conversations WHERE client_id=%s", (tg_client_id,))
