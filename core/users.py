from typing import List

from .db_connector import PrettyCursor


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


def get_admins_ids() -> List[int]:
    with PrettyCursor() as cursor:
        cursor.execute("SELECT tg_id FROM users WHERE is_admin")
        return [i[0] for i in cursor.fetchall()]
