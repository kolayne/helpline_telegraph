import psycopg2.errors
from typing import Tuple, Union

from db_connector import PrettyCursor


def add_user(tg_id: int) -> None:
    with PrettyCursor() as cursor:
        cursor.execute("INSERT INTO users(tg_id) VALUES (%s) ON CONFLICT DO NOTHING", (tg_id,))


def is_operator_and_is_not_crying(tg_id: int) -> bool:
    with PrettyCursor() as cursor:
        cursor.execute("SELECT user_is_operator(%s) AND NOT operator_is_crying(%s)", (tg_id, tg_id))
        return cursor.fetchone()[0]

def in_conversation_as(tg_client_id: int) -> Union[str, None]:
    """
    Check if the user is in a conversation as a client, as an operator, or not in a conversation

    Note that this function is not thread-safe. It's possible that the user has been in a conversation as a client and
    becomes then an operator, it's possible, that the function will return `None`. However, such situation is impossible
    due to logical invariants of users existence (it is only possible that a user first leaves a conversation and then
    joins a new onr with a new role, but if both happens very fast, it's ok if we are told that the user is not in a
    conversation, because we would get the same result from a perfect thread-safe atomic function if we have called it
    at the moment when the user has left one conversation, but hasn't yet joined another one, so I don't think this is
    an issue

    :param tg_client_id: Telegram id of the user to search for
    :return: `'operator'` if chatting as an operator, `'client'` if chatting as a client, `None` if not in a
        conversation
    """
    with PrettyCursor() as cursor:
        cursor.execute("SELECT EXISTS(SELECT 1 FROM conversations WHERE operator_id=%s)", (tg_client_id,))
        if cursor.fetchone()[0]:
            return 'operator'
        cursor.execute("SELECT EXISTS(SELECT 1 FROM conversations WHERE client_id=%s)", (tg_client_id,))
        if cursor.fetchone()[0]:
            return 'client'


def start_conversation(tg_client_id: int) -> Tuple[int, int]:
    """
    Start conversation with an operator

    :param tg_client_id: Telegram id of the user starting a conversation
    :return: If the given user is in a conversation already, `(-1, -1)` is returned. If the given user is in
        conversation(s) as an operator (an operator who is currently a client), `(-2, -2)` is returned. Otherwise a
        tuple where first element is the <b>telegram</b> operator id and the second is the <b>local</b> client id
    """
    with PrettyCursor() as cursor:
        try:
            cursor.execute("INSERT INTO conversations(client_id, operator_id) SELECT %s, tg_id FROM users WHERE "
                           "user_is_operator(tg_id) AND NOT operator_is_crying(tg_id) AND %s != tg_id ORDER BY "
                           "random() LIMIT 1",
                           (tg_client_id, tg_client_id))
            # TODO: handle case when no operators were selected for the conversation
        except psycopg2.errors.UniqueViolation:
            return -1, -1
        except psycopg2.errors.CheckViolation:
            return -2, -2
        else:
            cursor.execute("SELECT operator_id FROM conversations WHERE client_id=%s", (tg_client_id,))
            tg_operator_id, = cursor.fetchone()
            cursor.execute("SELECT local_id FROM users WHERE tg_id=%s", (tg_client_id,))
            local_client_id, = cursor.fetchone()
            return tg_operator_id, local_client_id

def end_conversation(tg_client_id: int) -> Union[Tuple[int, int], None]:
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


def get_operator_id(tg_client_id: int) -> int:
    with PrettyCursor() as cursor:
        cursor.execute("SELECT operator_id FROM conversations WHERE client_id=%s", (tg_client_id,))
        return cursor.fetchone()[0]
