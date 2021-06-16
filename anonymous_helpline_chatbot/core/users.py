from typing import List

from .db_connector import DatabaseConnectionPool


class UsersController:
    def __init__(self, database_connection_pool: DatabaseConnectionPool):
        self._conn_pool = database_connection_pool

    def add_user(self, chat_id: int) -> None:
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("INSERT INTO users(chat_id) VALUES (%s) ON CONFLICT DO NOTHING", (chat_id,))

    def get_local_id(self, chat_id: int) -> int:
        """
        Retrieves the local id of the user with the known messenger id

        :param chat_id: Messenger identifier of the user
        :return: Local identifier of the user with the given id
        """
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("SELECT local_id FROM users WHERE chat_id=%s", (chat_id,))
            return cursor.fetchone()[0]

    def is_operator(self, chat_id: int) -> bool:
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("SELECT is_admin FROM users WHERE chat_id = %s", (chat_id,))
            return cursor.fetchone()[0]

    def get_admins_ids(self) -> List[int]:
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("SELECT chat_id FROM users WHERE is_admin")
            return [i[0] for i in cursor.fetchall()]
