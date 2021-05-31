from contextlib import contextmanager

from psycopg2 import connect
from psycopg2.extensions import cursor as cursor_type


class DatabaseConnectionPool:
    # TODO: rewrite this class
    # This is only a draft version of a connection pool. It is going to be rewritten later (see issue #34)

    def __init__(self, host: str, db_name: str, username: str, password: str):
        self.host = host
        self.db_name = db_name
        self.username = username
        self.password = password

        # Ping
        with self.PrettyCursor() as cursor:
            cursor.execute("SELECT 1")

    @contextmanager
    def PrettyCursor(self) -> cursor_type:
        conn = connect(host=self.host, dbname=self.db_name, user=self.username, password=self.password)
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()
            conn.commit()
            conn.close()
