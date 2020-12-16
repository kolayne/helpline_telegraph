import psycopg2.errors
from typing import Tuple, Optional, List
from threading import Lock

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
        # TODO: remove user from conversation expecters


def get_admins_ids() -> List[int]:
    with PrettyCursor() as cursor:
        cursor.execute("SELECT tg_id FROM users WHERE is_admin")
        return [i[0] for i in cursor.fetchall()]


# Whenever a client wants to have a conversation all the operators get a message which invites him to the conversation
# with the client. Whenever an operator accepts the invitation, all the invitations messages for other operators are
# deleted.
# `operators_invitations_messages` is used for storing sent invitations messages for being able to delete them later. It
# is a dictionary from telegram client id to a list of tuples of telegram operator chat id and telegram id of a message,
# which invites the operator to join a conversation with the client (simpler `{client_id: [(operator_id, message_id)]}`)
operators_invitations_messages = {}
# `clients_expecting_operators` is a set of telegram ids of clients waiting for an operator to start chatting with
clients_expecting_operators = set()
# `conversation_starter_lock` is a lock which must be acquired when working with `operators_invitations_messages` and/or
# `clients_expecting_operators`
conversation_starter_lock = Lock()


def invite_operators(tg_client_id: int) -> int:
    # TODO: add docs

    raise NotImplementedError("This function is just a scratch, not the real code (yet)")

    if get_conversing(tg_client_id) != ((None, None), (None, None)):  # In a conversation already
        return False

    with conversation_starter_lock:
        first_len = len(clients_expecting_operators)
        clients_expecting_operators.add(tg_client_id)

        # If no new element was added, which means this client has requested an operator is awaited already
        if first_len == len(clients_expecting_operators):
            return 1

    free_operators = "list of all free operators"  # TODO
    if not free_operators:
        return 2

    msg_ids = []
    for tg_operator_id in free_operators:
        try:
            msg_ids.append((
                tg_operator_id,
                bot.send_message(tg_operator_id, "Hey, come join us by clicking the button or something")
            ))
        except Exception:  # TODO only catch telegram api exceptions
            pass  # TODO: log

    with conversation_starter_lock:
        operators_invitations_messages[tg_operator_id] = \
            operators_invitations_messages.get(tg_operator_id, []) + msg_ids

    return 0


def start_conversation(tg_client_id: int, tg_operator_id: int) -> bool:
    """
    Start conversation with an operator

    :param tg_client_id: Telegram id of the client to start conversation with
    :param tg_operator_id: Telegram id of the operator to start conversation with
    :return: `True` if the conversation was started successfully, `False` if an `IntegrityError` exception was raised.
        `False` could also be returned under some other circumstances when it's impossible to start the conversation
        (i. e. some of the users are in conversations already, etc) even if there where no exception from `psycopg`
    """
    # Must check for this separately, because if the given client is chatting with an operator and no operators are
    # available, the rest of the code is going to return an incorrect code (`0` instead of `1`) even though the database
    # will stay correct
    if get_conversing(tg_client_id)[0][0] == tg_client_id:
        return False

    with PrettyCursor() as cursor:
        try:
            cursor.execute("INSERT INTO conversations(client_id, operator_id) VALUES (?, ?)",
                           (tg_client_id, tg_operator_id))
        except psycopg2.errors.IntegrityError:
            return False
        else:
            return True
