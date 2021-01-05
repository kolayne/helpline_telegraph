import psycopg2.errors
from typing import Tuple, List, Union

from db_connector import PrettyCursor


def add_user(tg_id: int) -> None:
    with PrettyCursor() as cursor:
        cursor.execute("INSERT INTO users(tg_id) VALUES (%s) ON CONFLICT DO NOTHING", (tg_id,))

def get_local_id(tg_id: int) -> int:
    """
    Retrieves the local id of the user with the known telegram id

    :param tg_id: Telegram identifier of the user
    :return: Local identifier of the user with the given id
    """
    with PrettyCursor() as cursor:
        cursor.execute("SELECT local_id FROM users WHERE tg_id=%s", (tg_id,))
        return cursor.fetchone()[0]


def get_free_operators() -> List[int]:
    """
    Retrieves telegram ids of operators who are currently not in any conversation
    :return: `list` of telegram ids of free operators
    """
    with PrettyCursor() as cursor:
        cursor.execute("SELECT tg_id FROM users WHERE is_operator AND NOT "
                       "(operator_is_crying(tg_id) OR operator_is_operating(tg_id))")
        return [i[0] for i in cursor.fetchall()]


def get_conversing(tg_id: int) -> Union[Tuple[Tuple[int, int], Tuple[int, int]],
                                        Tuple[Tuple[None, None], Tuple[None, None]]]:
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
            return (None, None), (None, None)
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


def begin_conversation(tg_client_id: int, tg_operator_id: int) -> bool:
    """
    Begins a conversation between a client and an operator

    :param tg_client_id: Telegram id of the client to start conversation with
    :param tg_operator_id: Telegram id of the operator to start conversation with
    :return: `True` if the conversation was started successfully, `False` otherwise (<b>for example</b>, if either the
        client or the operator is busy). Formally, `False` is returned if the `psycopg2.errors.IntegrityError` exception
        was raised, `True` if there were no exceptions (which means, `False` will be returned if there is
        <b>anything</b> wrong with the request, e. g. the user with the `tg_operator_id` identifier is not an operator)
    """
    with PrettyCursor() as cursor:
        try:
            cursor.execute("INSERT INTO conversations(client_id, operator_id) VALUES (%s, %s)",
                           (tg_client_id, tg_operator_id))
        except psycopg2.errors.IntegrityError:  # Either this operator or this client is busy, or something else is bad
            return False
        else:
            return True
