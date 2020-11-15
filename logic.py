import psycopg2.errors
from typing import Tuple, Optional

from db_connector import PrettyCursor


def add_user(tg_id: int) -> None:
    with PrettyCursor() as cursor:
        cursor.execute("INSERT INTO users(tg_id) VALUES (%s) ON CONFLICT DO NOTHING", (tg_id,))


def is_operator_and_is_not_crying(tg_id: int) -> bool:
    with PrettyCursor() as cursor:
        cursor.execute("SELECT user_is_operator(%s) AND NOT operator_is_crying(%s)", (tg_id, tg_id))
        return cursor.fetchone()[0]


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


def start_conversation(tg_client_id: int) -> int:
    """
    Start conversation with an operator

    :param tg_client_id: Telegram id of the user starting a conversation
    :return: `0` on success, `1` if the client is already crying (in conversation as a client), `2` if the client is
        operating, `3` if there are no operators available
    """
    # Must check for this separately, because if the given client is chatting with an operator and no operators are
    # available, the rest of the code is going to return an incorrect code (`0` instead of `1`) even though the database
    # will stay correct
    if get_conversing(tg_client_id)[0][0] == tg_client_id:
        return 1

    with PrettyCursor() as cursor:
        try:
            cursor.execute("INSERT INTO conversations(client_id, operator_id) SELECT %s, tg_id FROM users WHERE "
                           "user_is_operator(tg_id) AND %s != tg_id AND "
                           "NOT exists(SELECT 1 FROM conversations WHERE client_id=tg_id OR operator_id=tg_id) "
                           "ORDER BY random() LIMIT 1",
                           (tg_client_id, tg_client_id))
        except psycopg2.errors.UniqueViolation:
            return 1  # Client is in conversation already
        except psycopg2.errors.CheckViolation as e:
            if 'client_is_not_operating' in e.pgerror:
                return 2  # The client is operating

            return -1  # Unexpected check violation

    if get_conversing(tg_client_id)[0][0] == -1:
        return 3  # No operators available

    return 0

def end_conversation(tg_client_id: int) -> Optional[Tuple[int, int]]:
    """
    Stop conversation with an operator

    Note that this function can only be called with a client id. Operator is unable to end a conversation in current
    implementation.

    :param tg_client_id: Telegram id of the client ending the conversation
    :return: If there is no conversation with the given user as a client, `None` is returned. Otherwise a tuple of two
        elements is returned, where the first element is the <b>telegram</b> id of the operator of the conversation,
        the second is the <b>local</b> client id
    """
    with PrettyCursor() as cursor:
        cursor.execute("SELECT operator_id, (SELECT local_id FROM users WHERE tg_id=%s) FROM conversations WHERE "
                       "client_id=%s", (tg_client_id, tg_client_id))
        ans = cursor.fetchone()

        cursor.execute("DELETE FROM conversations WHERE client_id=%s", (tg_client_id,))

        return ans
