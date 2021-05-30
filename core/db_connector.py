from contextlib import contextmanager

from psycopg2 import connect
from psycopg2.extensions import cursor as cursor_type

from ..config import db_host, db_name, db_username, db_password


@contextmanager
def PrettyCursor() -> cursor_type:
    conn = connect(host=db_host, dbname=db_name, user=db_username, password=db_password)
    cursor = conn.cursor()
    try:
        yield cursor
    finally:
        cursor.close()
        conn.commit()
        conn.close()
