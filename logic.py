import psycopg2.errors
from typing import Tuple, List

from db_connector import PrettyCursor


def add_user(tg_id: int) -> None:
    with PrettyCursor() as cursor:
        cursor.execute("INSERT INTO users(tg_id) VALUES (%s) ON CONFLICT DO NOTHING", (tg_id,))


def get_conversing(tg_id: int) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """
    Get client and operator from a conversation with the given identifier

    Retrieves both telegram and local identifiers of both client and operator of the conversation, in which the given
    user takes part. This function can be used for understanding whether current user is a client or an operator in his
    conversation, getting information about his interlocutor, etc

    :param tg_id: Telegram identifier of either a client or an operator
    :return: If there given user is not in conversation, `((None, None), (None, None))` is returned. Otherwise a tuple
        of two tuples is returned, where the first tuple describes the client, the second tuple describes the operator,
        and each of them consists of two `int`s, the first of which is the telegram id of a person, the second is the
        local id
    """
    with PrettyCursor() as cursor:
        cursor.execute("SELECT client_id,   (SELECT local_id FROM users WHERE tg_id=client_id), "
                       "       operator_id, (SELECT local_id FROM users WHERE tg_id=operator_id) "
                       "FROM conversations WHERE client_id=%s OR operator_id=%s",
                       (tg_id, tg_id))
        try:
            a, b, c, d = cursor.fetchone()
        except TypeError:
            return (-1, -1), (-1, -1)
        return (a, b), (c, d)


def end_conversation(tg_client_id: int) -> None:
    """
    End the conversation between the client and an operator if there is any

    Note that this function can only be called with a client id. Operator is unable to end a conversation in current
    implementation.

    :param tg_client_id: Telegram id of the client ending the conversation
    """
    with PrettyCursor() as cursor:
        cursor.execute("DELETE FROM conversations WHERE client_id=%s", (tg_client_id,))


def get_admins_ids() -> List[int]:
    with PrettyCursor() as cursor:
        cursor.execute("SELECT tg_id FROM users WHERE is_admin")
        return [i[0] for i in cursor.fetchall()]


def start_conversation(tg_client_id: int, tg_operator_id: int) -> bool:
    """
    Start conversation with an operator

    :param tg_client_id: Telegram id of the client to start conversation with
    :param tg_operator_id: Telegram id of the operator to start conversation with
    :return: `True` if the conversation was started successfully, `False` if an `IntegrityError` exception was raised.
        `False` could also be returned under some other circumstances when it's impossible to start the conversation
        (i. e. some of the users are in conversations already, etc) even if there where no exception from `psycopg`
    """
    with PrettyCursor() as cursor:
        try:
            cursor.execute("INSERT INTO conversations(client_id, operator_id) VALUES (?, ?)",
                           (tg_client_id, tg_operator_id))
        except psycopg2.errors.IntegrityError:  # Either this operator or this client is busy
            return False
        else:
            return True
