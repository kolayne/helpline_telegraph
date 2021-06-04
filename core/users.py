from typing import List

from .db_connector import DatabaseConnectionPool


class UsersController:
    def __init__(self, database_connection_pool: DatabaseConnectionPool):
        self._conn_pool = database_connection_pool

    def add_user(self, tg_id: int) -> None:
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("INSERT INTO users(chat_id) VALUES (%s) ON CONFLICT DO NOTHING", (tg_id,))

    def get_local_id(self, tg_id: int) -> int:
        """
        Retrieves the local id of the user with the known telegram id

        :param tg_id: Telegram identifier of the user
        :return: Local identifier of the user with the given id
        """
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("SELECT local_id FROM users WHERE chat_id=%s", (tg_id,))
            return cursor.fetchone()[0]

    def get_free_operators(self) -> List[int]:
        """
        Retrieves telegram ids of operators who are currently not in any conversation
        :return: `list` of telegram ids of free operators
        """
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("SELECT chat_id FROM users WHERE is_operator AND NOT "
                           "(operator_is_crying(chat_id) OR operator_is_operating(chat_id))")
            return [i[0] for i in cursor.fetchall()]

    def get_admins_ids(self) -> List[int]:
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("SELECT chat_id FROM users WHERE is_admin")
            return [i[0] for i in cursor.fetchall()]
