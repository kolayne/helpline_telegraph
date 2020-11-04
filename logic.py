import psycopg2.errors
from typing import Tuple

from db_connector import PrettyCursor


def add_user(tg_id: int) -> None:
    with PrettyCursor() as cursor:
        cursor.execute("INSERT INTO users(tg_id, type) VALUES (%s , 'client') ON CONFLICT DO NOTHING", (tg_id,))


def start_conversation(tg_client_id: int) -> Tuple[int, int]:
    """Start conversation with an operator

    :param tg_client_id: Telegram id of the user starting a conversation
    :return: If the given user is in a conversation already, `(-1, -1)` is returned. If the given user is not a client,
            `(-2, -2)` is returned. Otherwise a tuple where first element is the <b>telegram</b> operator id and the
            second is the <b>local</b> client id
    """
    with PrettyCursor() as cursor:
        try:
            cursor.execute("INSERT INTO conversations(client_id, operator_id) SELECT %s, tg_id FROM users WHERE "
                           "type='operator' ORDER BY random() LIMIT 1", (tg_client_id,))
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
